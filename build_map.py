#!/usr/bin/env python3
"""
Builds the City Council bill-support map from your Google Sheet and writes it to site/index.html.
The GitHub Action (update-map.yml) runs this, password-protects the result and publishes it.

Settings (colors, labels, column names) are in settings.py. The Sheet link comes from the SHEET_URL
environment variable (a GitHub secret). Nothing in this file needs editing.

Run  python build_map.py --tune  on your own computer to add a panel of sliders for the heatmap and
sweeps shading. The panel redraws the map as you drag and shows the settings.py lines to copy back.

Logs on a public repo are public, so this script only prints district numbers, column headers and
malformed cell values, never names, notes or the Sheet link.
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
import folium
from branca.element import Element
from settings import *

SHEET_URL = os.environ.get("SHEET_URL", "").strip()

# Heatmap settings. Defaults are used if settings.py doesn't define them.
def _opt(name, default):
    return globals().get(name, default)

HEAT_FILE = _opt("HEAT_FILE", "data/heat.json")            # made by make_heat_json.py
HEAT_SHOW_AT_START = _opt("HEAT_SHOW_AT_START", False)
HEAT_HEADING = _opt("HEAT_HEADING", "Arrests heatmap")
HEAT_LABEL = _opt("HEAT_LABEL", "Selected misdemeanor arrests")
HEAT_RADIUS = _opt("HEAT_RADIUS", 18)                      # blob size in pixels
HEAT_BLUR = _opt("HEAT_BLUR", 15)
HEAT_MAX_ZOOM = _opt("HEAT_MAX_ZOOM", 15)                  # zoom level at which points reach full strength
HEAT_MIN_OPACITY = _opt("HEAT_MIN_OPACITY", 0.25)
HEAT_MAX = _opt("HEAT_MAX", 1.0)                           # lower = hotter overall
HEAT_PERCENTILE = _opt("HEAT_PERCENTILE", 95)              # cells at/above this percentile show at full intensity
HEAT_GRADIENT = _opt("HEAT_GRADIENT", {0.2: "#bfd3ff", 0.5: "#6f7bff", 0.8: "#5b1fb8", 1.0: "#2a0a5e"})

BHEARD_PRECINCTS = _opt("BHEARD_PRECINCTS", [])
BHEARD_PRECINCT_FILE = _opt("NYPD_PRECINCT_FILE", "data/police_precincts.geojson")
BHEARD_SHOW_AT_START = _opt("BHEARD_SHOW_AT_START", False)
BHEARD_HEADING = _opt("BHEARD_HEADING", "B HEARD")
BHEARD_LABEL = _opt("BHEARD_LABEL", "B HEARD precincts")
BHEARD_STYLE = _opt("BHEARD_STYLE", dict(color="#00008B", weight=2.5, dashArray="6 4", fillOpacity=0.08))

DHS_SWEEPS_FOLDER = _opt("DHS_SWEEPS_FOLDER", "data/dhs_sweeps/")   # quarterly DHS LL34 .xlsx reports
SWEEPS_SHOW_AT_START = _opt("SWEEPS_SHOW_AT_START", False)
SWEEPS_HEADING = _opt("SWEEPS_HEADING", "Encampment sweeps")
SWEEPS_LABEL = _opt("SWEEPS_LABEL", "DHS encampment sweeps")
SWEEPS_METRIC = _opt("SWEEPS_METRIC", "sweeps")            # "sweeps" or "people"
SWEEPS_PERCENTILE = _opt("SWEEPS_PERCENTILE", 90)
SWEEPS_COLOR = _opt("SWEEPS_COLOR", "#BB1F00")
SWEEPS_OPACITY = _opt("SWEEPS_OPACITY", 0.85)

TUNE = "--tune" in sys.argv
OUT_FILE = Path("site") / "index.html"

# NYC Open Data: City Council Districts (NYC Dept. of City Planning, clipped to shoreline)
COUNCIL_DATASET = "872g-cjhh"
# NYC Open Data: Police Precincts (NYPD)
PRECINCT_DATASET = "y76i-bdw7"
GEOJSON_URL = "https://data.cityofnewyork.us/api/geospatial/{id}?method=export&format=GeoJSON"
FIELD_CANDIDATES = ["coundist", "council_dist", "district", "dist"]

def _round(c, nd=4):  # ~11 m precision keeps the map light
    return round(c, nd) if isinstance(c, (int, float)) else [_round(x, nd) for x in c]

def fetch_geojson(cache_file, dataset_id):
    """Returns the GeoJSON in cache_file if it exists, otherwise downloads the NYC Open Data dataset."""
    cache = Path(cache_file)   # optional: commit a copy here to skip the download
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    last = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(GEOJSON_URL.format(id=dataset_id),
                                         headers={"User-Agent": "nyc-district-map/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"Boundary download attempt {attempt} failed: {type(e).__name__}")
            time.sleep(5 * attempt)
    raise RuntimeError(f"Could not download boundary dataset {dataset_id}: {type(last).__name__}")

def load_council():
    try:
        gj = fetch_geojson(COUNCIL_FILE, COUNCIL_DATASET)
    except RuntimeError as e:
        sys.exit(str(e))
    feats = [f for f in gj["features"] if f.get("geometry")]
    lower = {k.lower(): k for k in feats[0]["properties"]}
    field = next((lower[c] for c in FIELD_CANDIDATES if c in lower), None)
    if field is None:
        raise ValueError(f"Can't find the district-number field. Properties found: {list(lower)}")
    out = []
    for f in feats:
        try:
            d = int(float(f["properties"][field]))
        except (TypeError, ValueError):
            continue
        g = f["geometry"]
        out.append({"district": d, "type": g["type"], "coordinates": _round(g["coordinates"])})
    return sorted(out, key=lambda f: f["district"])


# ===== Read the Sheet and draw the map (no need to edit) =====
def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()

def is_on(v):
    return norm(v) not in FALSE_VALUES

def flag_text(v):
    if not is_on(v):
        return LABELS["no"]
    return LABELS["yes"] if norm(v) in YES_VALUES else str(v).strip()

def read_sheet(sheet_id, tab):
    url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv&sheet=%s"
           % (sheet_id, urllib.parse.quote(tab)))
    try:
        df = pd.read_csv(url, dtype=str).fillna("")
    except Exception as e:
        raise RuntimeError(
            f"Couldn't read the '{tab}' tab ({getattr(e, 'code', type(e).__name__)}). Check that sharing is 'Anyone with the link: Viewer' "
            f"and that the tab is named exactly '{tab}' (SHEET_TAB in Settings).") from None
    return df

def label_point(coords, gtype):
    polys = coords if gtype == "MultiPolygon" else [coords]
    ring = max((p[0] for p in polys), key=len)
    xs, ys = [c[0] for c in ring], [c[1] for c in ring]
    return [(min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2]

CSS = """<style>
.panel{background:#fff;border:1px solid #c5ccd3;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.2);
 font:13px/1.35 Arial,sans-serif;padding:10px 12px;color:#1f2933}
.legend{width:290px;max-height:calc(100vh - 30px);overflow-y:auto}
.legend h2{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#52606d;margin:12px 0 4px}
.legend h2:first-child{margin-top:0}
.opt,.keyrow{display:flex;align-items:center;gap:7px;padding:2px 0}
.opt{cursor:pointer}.keyrow{padding-left:22px}
.opt input{margin:0}.t{flex:1}.n{color:#52606d;font-variant-numeric:tabular-nums}
.sw{display:inline-block;width:18px;height:18px;border-radius:3px;border:1px solid rgba(0,0,0,.35);
 background-color:#fff;flex:none;box-sizing:border-box}
.key{margin:2px 0 0}
.hint{color:#52606d;font-size:11px;margin:2px 0 0 25px}
canvas.leaflet-heatmap-layer{pointer-events:none!important}
.dlabel{font:600 11px Arial,sans-serif;color:#111;white-space:nowrap;text-align:center;
 text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;pointer-events:none!important}
.nolabels .dlabel{display:none}
.info{min-width:230px}.info h3{margin:0 0 6px;font-size:16px}
.info table{border-collapse:collapse;width:100%}
.info th{text-align:left;font-weight:normal;color:#52606d;padding:2px 10px 2px 0;vertical-align:top;white-space:nowrap}
.info td{padding:2px 0}
.chip{display:inline-block;padding:1px 9px;border-radius:10px;font-weight:600;border:1px solid rgba(0,0,0,.25)}
.tune{width:250px;font-size:12px}.tune h2{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#52606d;margin:10px 0 4px}
.tune h2:first-child{margin-top:0}.tune label{display:flex;align-items:center;gap:6px;margin:3px 0}
.tune label span{width:86px;flex:none}.tune input[type=range]{flex:1;min-width:0}.tune output{width:38px;text-align:right;font-variant-numeric:tabular-nums}
.tune textarea{width:100%;box-sizing:border-box;height:150px;font:11px/1.3 Menlo,monospace;margin-top:6px}
@media(max-width:700px){.legend{width:210px;max-height:55vh;font-size:12px}}
</style>"""

JS = r"""
(function boot() {
  const m0 = window['__MAPNAME__'];
  if (!window.L || !m0 || !m0.getSize) { setTimeout(boot, 30); return; }
  init(m0);
})();

function init(map) {
  const CFG = __CFG__;
  const NS = 'http://www.w3.org/2000/svg';
  const DASH = '\u2014';
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const T = CFG.labels;
  const fc = CFG.features;
  const statusColor = {}, statusLabel = {};
  CFG.statuses.forEach(s => { statusColor[s.key] = s.color; statusLabel[s.key] = s.label; });
  const state = {bill: CFG.defaultBill, committee: null, budget: false, bnt: false, sio: false, pc: false, heat: false, sweeps: false, bheard: false};

  const seen = new Set(), U = [];
  fc.features.forEach(f => { const d = f.properties.district; if (!seen.has(d)) { seen.add(d); U.push(f.properties); } });

  [['pCommittee', 410], ['pBnt', 411], ['pSio', 420], ['pPc', 421], ['pBheard', 422], ['pHeat', 450]].forEach(function (a) {
    const pane = map.createPane(a[0]); pane.style.zIndex = a[1]; pane.style.pointerEvents = 'none';
  });

  // ---------- info box and tooltip ----------
  const chip = (text, color) => '<span class="chip" style="background:' + color + '">' + esc(text) + '</span>';
  const repName = p => esc(p.rep) || esc(T.noRep);
  function popupHtml(p) {
    const rows = [];
    const row = (k, v) => rows.push('<tr><th>' + esc(k) + '</th><td>' + v + '</td></tr>');
    row(T.district, esc(p.district));
    row(T.party, esc(p.party) || DASH);
    CFG.bills.forEach(function (name, i) {
      const k = p.billKeys[i];
      row(name, k ? chip(statusLabel[k], statusColor[k]) : chip(p.billRaw[i] || T.noData, CFG.colors.noData));
    });
    row(T.budget, esc(p.budgetText));
    CFG.committees.forEach((name, i) => row(name, esc(p.committeeText[i])));
    row(T.bnt, esc(p.bntText));
    row(T.sio, esc(p.sioText));
    row(T.pc, esc(p.pcText));
    if (CFG.sweeps) row(CFG.sweeps.heading, esc(p.sweeps) + ' sweeps, ' + esc(p.sweepPeople) + ' people affected');
    row(T.notes, '<span style="white-space:pre-wrap">' + (esc(p.notes) || DASH) + '</span>');
    return '<div class="info"><h3>' + repName(p) + '</h3><table>' + rows.join('') + '</table></div>';
  }
  const tipHtml = p => '<b>' + repName(p) + '</b><br>' + esc(T.district) + ' ' + esc(p.district) + (p.party ? ' \u00b7 ' + esc(p.party) : '');

  // ---------- base layer: fill colour, hover, click ----------
  // ---------- encampment sweeps shading (scaled so the top percentile gets the darkest shade) ----------
  const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mix = (a, b, t) => '#' + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, '0')).join('');
  const sweepVal = p => CFG.sweeps.metric === 'people' ? p.sweepPeople : p.sweeps;
  function pctCap(values, pct) {
    const v = values.slice().sort((a, b) => a - b);
    return v.length ? Math.max(1, v[Math.min(v.length - 1, Math.floor(v.length * pct / 100))]) : 1;
  }
  let sweepCap = 1;
  const sweepRamp = () => [mix(hexRgb('#ffffff'), hexRgb(CFG.sweeps.color), 0.12), CFG.sweeps.color];
  function sweepColor(p) {
    const v = sweepVal(p);
    if (!v) return CFG.colors.neutral;
    const r = sweepRamp();
    return mix(hexRgb(r[0]), hexRgb(r[1]), Math.min(v / sweepCap, 1));
  }
  function updateSweepCap() {
    if (!CFG.sweeps) return;
    sweepCap = pctCap(U.map(sweepVal), CFG.sweeps.percentile);
    const el = legendEl && legendEl.querySelector('[data-hint="sweeps"]');
    if (el) el.textContent = (CFG.sweeps.note ? CFG.sweeps.note + '. ' : '') + 'Darkest = ' + sweepCap + '+ ' +
      (CFG.sweeps.metric === 'people' ? 'people affected' : 'sweeps') + '.';
  }

  function fillColor(p) {
    if (state.sweeps && CFG.sweeps) return sweepColor(p);
    if (state.budget && p.budget) return CFG.colors.budget;
    if (state.bill !== null) { const k = p.billKeys[state.bill]; return k ? statusColor[k] : CFG.colors.noData; }
    return CFG.colors.neutral;
  }
  const baseStyle = f => ({fillColor: fillColor(f.properties), fillOpacity: (state.sweeps && CFG.sweeps) ? CFG.sweeps.opacity : CFG.fillOpacity, color: CFG.colors.baseOutline, weight: 1, opacity: 1});
  const base = L.geoJSON(fc, {
    style: baseStyle,
    onEachFeature: function (f, l) {
      l.bindTooltip(tipHtml(f.properties), {sticky: true});
      l.bindPopup(popupHtml(f.properties), {maxWidth: 380});
      l.on('mouseover', () => l.setStyle({weight: 3, color: '#000'}));
      l.on('mouseout', () => base.resetStyle(l));
    }
  }).addTo(map);

  // ---------- overlay layers (not clickable, so clicks reach the base layer) ----------
  const overlay = (pane, style) => L.geoJSON(fc, {pane: pane, interactive: false, style: style}).addTo(map);
  const OFF = {stroke: false, fill: false};
  const committeeLayer = overlay('pCommittee', f => (state.committee !== null && f.properties.committees[state.committee])
    ? {stroke: false, fill: true, fillColor: 'url(#hatchCommittee)', fillOpacity: 1} : OFF);
  const bntLayer = overlay('pBnt', f => (state.bnt && f.properties.bnt)
    ? {stroke: false, fill: true, fillColor: 'url(#hatchBnt)', fillOpacity: 1} : OFF);
  const sioLayer = overlay('pSio', f => (state.sio && f.properties.sio)
    ? {stroke: true, fill: false, color: CFG.sio.color, weight: CFG.sio.weight, opacity: 1} : OFF);
  const pcLayer = overlay('pPc', f => (state.pc && f.properties.pc)
    ? {stroke: true, fill: false, color: CFG.pc.color, weight: CFG.pc.weight, opacity: 1} : OFF);
  const bheardLayer = CFG.bheard ? L.geoJSON(CFG.bheard.features, {pane: 'pBheard', interactive: false,
    style: () => Object.assign({fillColor: CFG.bheard.style.color, opacity: 1}, CFG.bheard.style)}) : null;

  function addPattern(layer, id, h) {
    const svg = map.getRenderer(layer)._container;
    let defs = svg.querySelector('defs');
    if (!defs) { defs = document.createElementNS(NS, 'defs'); svg.insertBefore(defs, svg.firstChild); }
    const pat = document.createElementNS(NS, 'pattern');
    pat.setAttribute('id', id);
    pat.setAttribute('patternUnits', 'userSpaceOnUse');
    pat.setAttribute('width', h.spacing); pat.setAttribute('height', h.spacing);
    pat.setAttribute('patternTransform', 'rotate(' + h.angle + ')');
    const ln = document.createElementNS(NS, 'line');
    ln.setAttribute('x1', 0); ln.setAttribute('y1', 0); ln.setAttribute('x2', 0); ln.setAttribute('y2', h.spacing);
    ln.setAttribute('stroke', h.color); ln.setAttribute('stroke-width', h.width);
    pat.appendChild(ln); defs.appendChild(pat);
  }
  addPattern(committeeLayer, 'hatchCommittee', CFG.committeeHatch);
  addPattern(bntLayer, 'hatchBnt', CFG.bntHatch);

  // ---------- district number labels ----------
  const labels = L.layerGroup();
  fc.features.forEach(function (f) {
    if (!f.properties.label) return;
    L.marker(f.properties.label, {interactive: false, keyboard: false,
      icon: L.divIcon({className: 'dlabel', html: String(f.properties.district), iconSize: [30, 14], iconAnchor: [15, 7]})}).addTo(labels);
  });
  if (CFG.labelsOn) labels.addTo(map);
  const syncLabels = () => map.getContainer().classList.toggle('nolabels', map.getZoom() < 11);
  map.on('zoomend', syncLabels); syncLabels();

  // ---------- arrests heatmap (optional: only present when data/heat.json exists) ----------
  let heatLayer = null;
  function loadHeatLib(ok, fail) {
    if (L.heatLayer) { ok(); return; }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.js';
    s.onload = ok; s.onerror = fail;
    document.head.appendChild(s);
  }
  function heatPoints() {
    const cap = pctCap(CFG.heat.points.map(p => p[2]), CFG.heat.percentile);
    return CFG.heat.points.map(p => [p[0], p[1], Math.min(p[2] / cap, 1)]);
  }
  function refreshHeat() {
    if (heatLayer) { heatLayer.setOptions(CFG.heat.options); heatLayer.setLatLngs(heatPoints()); }
  }
  function setHeat(on) {
    state.heat = on;
    if (!CFG.heat) return;
    if (!on) {
      if (heatLayer && map.hasLayer(heatLayer)) {
        // leaflet.heat removes its canvas from the overlay pane, so put it back there first.
        map.getPanes().overlayPane.appendChild(heatLayer._canvas);
        map.removeLayer(heatLayer);
      }
      return;
    }
    loadHeatLib(function () {
      if (!state.heat) return;
      if (!heatLayer) heatLayer = L.heatLayer(heatPoints(), CFG.heat.options);
      if (!map.hasLayer(heatLayer)) heatLayer.addTo(map);
      // leaflet.heat always draws in the overlay pane (z-index 400), under the hatching and outline
      // panes. Moving its canvas to pHeat puts it above every district layer.
      if (heatLayer._canvas) {
        heatLayer._canvas.style.pointerEvents = 'none';
        map.getPane('pHeat').appendChild(heatLayer._canvas);
      }
    }, function () {
      state.heat = false;
      const box = legendEl && legendEl.querySelector('[data-flag="heat"]');
      if (box) box.checked = false;
      setN('[data-n="heat"]', 'failed to load');
    });
  }

  // ---------- legend ----------
  let legendEl = null;
  const hatchCss = h => 'repeating-linear-gradient(' + (180 - h.angle) + 'deg,' + h.color + ' 0,' + h.color + ' ' + h.width + 'px,transparent ' + h.width + 'px,transparent ' + h.spacing + 'px)';
  const swHatch = h => '<span class="sw" style="background-image:' + hatchCss(h) + '"></span>';
  const swFill = c => '<span class="sw" style="background:' + c + '"></span>';
  const swLine = o => '<span class="sw" style="border:' + Math.min(o.weight, 4) + 'px solid ' + o.color + '"></span>';
  const radioOpt = (group, value, checked, swatch, text, nAttr) =>
    '<label class="opt"><input type="radio" name="' + group + '" value="' + value + '"' + (checked ? ' checked' : '') + '>' +
    swatch + '<span class="t">' + esc(text) + '</span><span class="n" ' + nAttr + '></span></label>';
  const checkOpt = (flag, swatch, text) =>
    '<label class="opt"><input type="checkbox" data-flag="' + flag + '">' + swatch +
    '<span class="t">' + esc(text) + '</span><span class="n" data-n="' + flag + '"></span></label>';

  function legendHtml() {
    let h = '<h2>' + esc(T.billHeading) + '</h2>';
    h += radioOpt('bill', -1, state.bill === null, '', T.none, '');
    CFG.bills.forEach((b, i) => { h += radioOpt('bill', i, state.bill === i, '', b, ''); });
    h += '<div class="key">';
    CFG.statuses.forEach(s => { h += '<div class="keyrow">' + swFill(s.color) + '<span class="t">' + esc(s.label) + '</span><span class="n" data-k="' + esc(s.key) + '"></span></div>'; });
    h += '<div class="keyrow">' + swFill(CFG.colors.noData) + '<span class="t">' + esc(T.noData) + '</span><span class="n" data-k="__none"></span></div></div>';
    h += '<h2>' + esc(T.budgetHeading) + '</h2>' + checkOpt('budget', swFill(CFG.colors.budget), T.budget);
    h += '<h2>' + esc(T.committeeHeading) + '</h2>' + radioOpt('committee', -1, true, '', T.none, '');
    CFG.committees.forEach((c, i) => { h += radioOpt('committee', i, false, swHatch(CFG.committeeHatch), c, 'data-c="' + i + '"'); });
    h += '<h2>' + esc(T.otherHeading) + '</h2>';
    h += checkOpt('bnt', swHatch(CFG.bntHatch), T.bnt) + checkOpt('sio', swLine(CFG.sio), T.sio) + checkOpt('pc', swLine(CFG.pc), T.pc);
    if (CFG.bheard) h += '<h2>' + esc(CFG.bheard.heading) + '</h2>' + checkOpt('bheard',
      '<span class="sw" style="border:2px dashed ' + CFG.bheard.style.color + '"></span>', CFG.bheard.label);
    if (CFG.sweeps) {
      const r = sweepRamp();
      h += '<h2>' + esc(CFG.sweeps.heading) + '</h2>' +
        checkOpt('sweeps', '<span class="sw" style="background:linear-gradient(90deg,' + r[0] + ',' + r[1] + ')"></span>', CFG.sweeps.label) +
        '<div class="hint" data-hint="sweeps"></div>';
    }
    if (CFG.heat) {
      const g = CFG.heat.options.gradient || {};
      const stops = Object.keys(g).sort((a, b) => a - b).map(k => g[k]).join(',');
      h += '<h2>' + esc(CFG.heat.heading) + '</h2>' +
        checkOpt('heat', '<span class="sw" style="background:linear-gradient(90deg,' + stops + ')"></span>', CFG.heat.label);
      if (CFG.heat.note) h += '<div class="hint">' + esc(CFG.heat.note) + '</div>';
    }
    h += '<label class="opt" style="margin-top:10px"><input type="checkbox" id="lbl"' + (CFG.labelsOn ? ' checked' : '') + '><span class="t">' + esc(T.showNumbers) + '</span></label>';
    return h;
  }
  function setN(sel, v) {
    const el = legendEl.querySelector(sel);
    if (el) el.textContent = (v === '' ? '' : '(' + v + ')');
  }
  function renderCounts() {
    CFG.statuses.forEach(s => setN('[data-k="' + s.key + '"]', state.bill === null ? '' : U.filter(p => p.billKeys[state.bill] === s.key).length));
    setN('[data-k="__none"]', state.bill === null ? '' : U.filter(p => !p.billKeys[state.bill]).length);
  }
  function staticCounts() {
    ['budget', 'bnt', 'sio', 'pc'].forEach(k => setN('[data-n="' + k + '"]', U.filter(p => p[k]).length));
    CFG.committees.forEach((c, i) => setN('[data-c="' + i + '"]', U.filter(p => p.committees[i]).length));
    if (CFG.bheard) setN('[data-n="bheard"]', CFG.bheard.features.features.length);
  }

  function redraw() {
    base.setStyle(baseStyle);
    committeeLayer.setStyle(committeeLayer.options.style);
    bntLayer.setStyle(bntLayer.options.style);
    sioLayer.setStyle(sioLayer.options.style);
    pcLayer.setStyle(pcLayer.options.style);
    if (bheardLayer) { if (state.bheard) bheardLayer.addTo(map); else map.removeLayer(bheardLayer); }
    renderCounts();
  }
  function onChange(e) {
    const t = e.target;
    if (t.id === 'lbl') { if (t.checked) labels.addTo(map); else map.removeLayer(labels); return; }
    if (t.name === 'bill') state.bill = (+t.value < 0) ? null : +t.value;
    else if (t.name === 'committee') state.committee = (+t.value < 0) ? null : +t.value;
    else if (t.dataset && t.dataset.flag === 'heat') { setHeat(t.checked); return; }
    else if (t.dataset && t.dataset.flag) state[t.dataset.flag] = t.checked;
    redraw();
  }

  const legend = L.control({position: 'topright'});
  legend.onAdd = function () {
    legendEl = L.DomUtil.create('div', 'panel legend');
    legendEl.innerHTML = legendHtml();
    L.DomEvent.disableClickPropagation(legendEl);
    L.DomEvent.disableScrollPropagation(legendEl);
    legendEl.addEventListener('change', onChange);
    return legendEl;
  };
  legend.addTo(map);

  staticCounts();
  updateSweepCap();
  [['bheard', CFG.bheard], ['sweeps', CFG.sweeps]].forEach(function (a) {
    if (!a[1] || !a[1].showAtStart) return;
    state[a[0]] = true;
    const box = legendEl.querySelector('[data-flag="' + a[0] + '"]');
    if (box) box.checked = true;
  });
  redraw();
  if (CFG.tune) addTuner();
  if (CFG.heat && CFG.heat.showAtStart) {
    const box = legendEl.querySelector('[data-flag="heat"]');
    if (box) box.checked = true;
    setHeat(true);
  }
  map.fitBounds(base.getBounds(), {paddingBottomRight: [map.getSize().x > 700 ? 300 : 0, 0]});

  // ---------- tuning panel (only in pages built with --tune) ----------
  function addTuner() {
    const ctl = [];
    if (CFG.heat) {
      const o = CFG.heat.options;
      ctl.push({h: CFG.heat.heading});
      ctl.push({k: 'HEAT_RADIUS', l: 'Radius', min: 2, max: 60, step: 1, get: () => o.radius, set: v => { o.radius = v; }, heat: 1});
      ctl.push({k: 'HEAT_BLUR', l: 'Blur', min: 1, max: 60, step: 1, get: () => o.blur, set: v => { o.blur = v; }, heat: 1});
      ctl.push({k: 'HEAT_MAX', l: 'Max', min: 0.01, max: 2, step: 0.01, get: () => o.max, set: v => { o.max = v; }, heat: 1});
      ctl.push({k: 'HEAT_MIN_OPACITY', l: 'Min opacity', min: 0, max: 1, step: 0.05, get: () => o.minOpacity, set: v => { o.minOpacity = v; }, heat: 1});
      ctl.push({k: 'HEAT_MAX_ZOOM', l: 'Max zoom', min: 8, max: 18, step: 1, get: () => o.maxZoom, set: v => { o.maxZoom = v; }, heat: 1});
      ctl.push({k: 'HEAT_PERCENTILE', l: 'Percentile', min: 50, max: 100, step: 1, get: () => CFG.heat.percentile, set: v => { CFG.heat.percentile = v; }, heat: 1});
    }
    if (CFG.sweeps) {
      const w = CFG.sweeps;
      ctl.push({h: w.heading});
      ctl.push({k: 'SWEEPS_METRIC', l: 'Measure', opts: ['sweeps', 'people'], get: () => w.metric, set: v => { w.metric = v; }});
      ctl.push({k: 'SWEEPS_PERCENTILE', l: 'Percentile', min: 50, max: 100, step: 1, get: () => w.percentile, set: v => { w.percentile = v; }});
      ctl.push({k: 'SWEEPS_OPACITY', l: 'Opacity', min: 0.1, max: 1, step: 0.05, get: () => w.opacity, set: v => { w.opacity = v; }});
    }
    const el = L.DomUtil.create('div', 'panel tune');
    let h = '';
    ctl.forEach(function (c, i) {
      if (c.h) { h += '<h2>Tune: ' + esc(c.h) + '</h2>'; return; }
      h += '<label><span>' + esc(c.l) + '</span>' + (c.opts
        ? '<select data-i="' + i + '">' + c.opts.map(v => '<option' + (v === c.get() ? ' selected' : '') + '>' + v + '</option>').join('') + '</select>'
        : '<input type="range" data-i="' + i + '" min="' + c.min + '" max="' + c.max + '" step="' + c.step + '" value="' + c.get() + '"><output>' + c.get() + '</output>') + '</label>';
    });
    el.innerHTML = h + '<textarea readonly></textarea>';
    const out = el.querySelector('textarea');
    const py = v => typeof v === 'string' ? '"' + v + '"' : String(v);
    const dump = () => { out.value = '# paste into settings.py\n' + ctl.filter(c => c.k).map(c => c.k + ' = ' + py(c.get())).join('\n'); };
    el.addEventListener('input', function (e) {
      const c = ctl[+e.target.dataset.i];
      if (!c) return;
      const v = c.opts ? e.target.value : +e.target.value;
      c.set(v);
      if (!c.opts) e.target.nextElementSibling.textContent = v;
      if (c.heat) {
        refreshHeat();
        if (!state.heat) { const b = legendEl.querySelector('[data-flag="heat"]'); if (b) b.checked = true; setHeat(true); }
      } else {
        updateSweepCap();
        if (!state.sweeps) { state.sweeps = true; const b = legendEl.querySelector('[data-flag="sweeps"]'); if (b) b.checked = true; }
        redraw();
      }
      dump();
    });
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.disableScrollPropagation(el);
    const t = L.control({position: 'bottomleft'});
    t.onAdd = () => el;
    t.addTo(map);
    dump();
  }
}
"""


def load_heat():
    """Reads data/heat.json (grid cells with arrest counts) if it exists; returns None otherwise."""
    path = Path(HEAT_FILE)
    if not path.exists():
        print(f"(no {HEAT_FILE} found, so the map is built without the heatmap layer)")
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    pts = raw.get("points", [])
    if not pts:
        print(f"! {HEAT_FILE} has no points; skipping the heatmap layer")
        return None
    counts = sorted(p[2] for p in pts)
    cap = max(1, counts[min(len(counts) - 1, int(len(counts) * HEAT_PERCENTILE / 100))])
    points = [[p[0], p[1], p[2]] for p in pts]   # raw counts; the page scales them by HEAT_PERCENTILE
    print(f"Heatmap: {len(points)} grid cells (full intensity at {cap}+ arrests per cell)")
    if len(points) > 150000:
        print("! That is a lot of cells; consider a coarser grid in make_heat_json.py to keep the page fast")
    return dict(
        points=points, heading=HEAT_HEADING, label=HEAT_LABEL, note=raw.get("note", ""),
        showAtStart=HEAT_SHOW_AT_START, percentile=HEAT_PERCENTILE,
        options=dict(radius=HEAT_RADIUS, blur=HEAT_BLUR, maxZoom=HEAT_MAX_ZOOM,
                     minOpacity=HEAT_MIN_OPACITY, max=HEAT_MAX, gradient=HEAT_GRADIENT),
    )


def load_bheard():
    """Returns the B HEARD precinct outlines for the page, or None if no precincts are listed or the download fails."""
    wanted = set(BHEARD_PRECINCTS)
    if not wanted:
        return None
    try:
        gj = fetch_geojson(BHEARD_PRECINCT_FILE, PRECINCT_DATASET)
    except RuntimeError as e:
        print(f"! {e}; skipping the B HEARD layer")
        return None
    feats = []
    for f in gj["features"]:
        try:
            pct = int(float(f["properties"].get("precinct")))
        except (TypeError, ValueError):
            continue
        g = f.get("geometry")
        if pct in wanted and g:
            feats.append({"type": "Feature", "properties": {"precinct": pct},
                          "geometry": {"type": g["type"], "coordinates": _round(g["coordinates"])}})
    missing = sorted(wanted - {f["properties"]["precinct"] for f in feats})
    if missing:
        print(f"! B HEARD precincts not found in the boundary file: {missing}")
    print(f"B HEARD: {len(feats)} precincts")
    return dict(heading=BHEARD_HEADING, label=BHEARD_LABEL, style=BHEARD_STYLE, showAtStart=BHEARD_SHOW_AT_START,
                features={"type": "FeatureCollection", "features": feats})


SWEEP_SHEETS = ["Line-Level Data", "Resolved"]        # the line-level tab's name changed in CY25Q3
SWEEP_DISTRICT_COLS = {"council dist", "council_dist", "city council districts"}


def read_sweep_report(path):
    """Returns the report's (district, people) rows, one per sweep, or None if no line-level tab is found."""
    xl = pd.ExcelFile(path)
    sheet = next((s for s in SWEEP_SHEETS if s in xl.sheet_names), None)
    if sheet is None:
        print(f"! {path.name}: no '{SWEEP_SHEETS[0]}' or '{SWEEP_SHEETS[1]}' tab, skipped")
        return None
    df = pd.read_excel(xl, sheet_name=sheet)
    cols = {norm(c): c for c in df.columns}
    dist = next((cols[c] for c in cols if c in SWEEP_DISTRICT_COLS), None)
    people = next((cols[c] for c in cols if c.startswith("clients affected")), None)
    if dist is None or people is None:
        print(f"! {path.name}: couldn't find the council district or clients affected column, skipped")
        return None
    return pd.DataFrame({"district": pd.to_numeric(df[dist], errors="coerce"),
                         "people": pd.to_numeric(df[people], errors="coerce")}).dropna()


def load_sweeps():
    """Returns (page settings, {district: {"sweeps", "people"}}) from the DHS reports, or (None, {}) if there are none.

    Only sweeps that affected at least one person are counted.
    """
    files = sorted(Path(DHS_SWEEPS_FOLDER).glob("*.xlsx"))
    if not files:
        print(f"(no .xlsx files in {DHS_SWEEPS_FOLDER}, so the map is built without the encampment sweeps layer)")
        return None, {}
    frames, quarters = [], []
    for f in files:
        df = read_sweep_report(f)
        if df is not None:
            frames.append(df)
            quarters.append(f.stem.split("_")[0])
    if not frames:
        return None, {}
    df = pd.concat(frames)
    df = df[df.people > 0]
    agg = df.groupby(df.district.astype(int)).people.agg(["count", "sum"])
    by_district = {int(d): {"sweeps": int(r["count"]), "people": int(r["sum"])} for d, r in agg.iterrows()}
    period = quarters[0] if len(quarters) == 1 else f"{quarters[0]}\u2013{quarters[-1]}"
    note = f"{int(agg['count'].sum()):,} sweeps, {period}"
    print(f"Encampment sweeps: {note}, {len(by_district)} districts")
    return dict(heading=SWEEPS_HEADING, label=SWEEPS_LABEL, note=note, metric=SWEEPS_METRIC,
                percentile=SWEEPS_PERCENTILE, color=SWEEPS_COLOR, opacity=SWEEPS_OPACITY,
                showAtStart=SWEEPS_SHOW_AT_START), by_district


def main():
    found = re.search(r"/d/([\w-]+)", SHEET_URL)
    if not found:
        raise ValueError("SHEET_URL doesn't look like a Google Sheets link (it should contain /d/...)")
    df = read_sheet(found.group(1), SHEET_TAB)
    colmap = {norm(c): c for c in df.columns}
    expected = list(COLS.values()) + [h for h, _ in BILLS] + [h for h, _ in COMMITTEES]
    missing_cols = [h for h in expected if norm(h) not in colmap]
    if norm(COLS["district"]) not in colmap:
        raise RuntimeError(f"No '{COLS['district']}' column in the '{SHEET_TAB}' tab. Headers found: {list(df.columns)}")
    if missing_cols:
        print("! These headers were not found in the Sheet (fix the spelling in the Settings cell, or the Sheet):")
        for h in missing_cols:
            print("    -", h)
        print("  Headers found:", list(df.columns))

    rows = {}
    for rec in df.to_dict("records"):
        try:
            rows[int(float(rec[colmap[norm(COLS["district"])]]))] = rec
        except ValueError:
            continue

    def cell(rec, header):
        c = colmap.get(norm(header))
        return str(rec.get(c, "")).strip() if c else ""

    status_by_key = {norm(k): k for k, _, _ in STATUSES}
    on_map = {f["district"] for f in FEATURES}
    for d in sorted(set(rows) - on_map):
        print(f"! District {d} is in the Sheet but not on the map")
    for d in sorted(on_map - set(rows)):
        print(f"! No Sheet row for district {d} (shown with no data)")

    sweeps_cfg, sweeps = load_sweeps()
    out, labelled = [], set()
    for f in FEATURES:
        d = f["district"]
        rec = rows.get(d, {})
        bill_raw = [cell(rec, h) for h, _ in BILLS]
        bill_keys = [status_by_key.get(norm(v)) for v in bill_raw]
        for (h, _), v, k in zip(BILLS, bill_raw, bill_keys):
            if v and k is None:
                print(f"! District {d}, {h}: unrecognized value '{v}' (shown as {LABELS['noData']})")
        comm_raw = [cell(rec, h) for h, _ in COMMITTEES]
        props = dict(
            district=d, rep=cell(rec, COLS["rep"]), party=cell(rec, COLS["party"]), notes=cell(rec, COLS["notes"]),
            billRaw=bill_raw, billKeys=bill_keys,
            budget=is_on(cell(rec, COLS["budget"])), budgetText=flag_text(cell(rec, COLS["budget"])),
            committees=[is_on(v) for v in comm_raw], committeeText=[flag_text(v) for v in comm_raw],
            bnt=is_on(cell(rec, COLS["bnt"])), bntText=flag_text(cell(rec, COLS["bnt"])),
            sio=is_on(cell(rec, COLS["sio"])), sioText=flag_text(cell(rec, COLS["sio"])),
            pc=is_on(cell(rec, COLS["pc"])), pcText=flag_text(cell(rec, COLS["pc"])),
            sweeps=sweeps.get(d, {}).get("sweeps", 0), sweepPeople=sweeps.get(d, {}).get("people", 0),
            label=None if d in labelled else label_point(f["coordinates"], f["type"]),
        )
        labelled.add(d)
        out.append({"type": "Feature", "properties": props,
                    "geometry": {"type": f["type"], "coordinates": f["coordinates"]}})

    cfg = dict(
        labels=LABELS,
        statuses=[dict(key=k, label=l, color=c) for k, l, c in STATUSES],
        bills=[l for _, l in BILLS], committees=[l for _, l in COMMITTEES],
        colors=dict(noData=NO_DATA_COLOR, neutral=NEUTRAL_FILL, baseOutline=BASE_OUTLINE_COLOR, budget=BUDGET_COLOR),
        committeeHatch=COMMITTEE_HATCH, bntHatch=BNT_HATCH, sio=SIO_OUTLINE, pc=PC_OUTLINE,
        fillOpacity=FILL_OPACITY, defaultBill=DEFAULT_BILL, labelsOn=SHOW_NUMBERS,
        heat=load_heat(), sweeps=sweeps_cfg, bheard=load_bheard(), tune=TUNE,
        features={"type": "FeatureCollection", "features": out},
    )

    m = folium.Map(location=[40.705, -73.96], zoom_start=10, tiles=None, control_scale=True)
    m.get_root().header.add_child(Element(CSS))
    blob = json.dumps(cfg, separators=(",", ":")).replace("</", "<\\/")
    m.get_root().script.add_child(Element(JS.replace("__CFG__", blob).replace("__MAPNAME__", m.get_name())))

    OUT_FILE.parent.mkdir(exist_ok=True)
    m.save(str(OUT_FILE))
    print(f"Wrote {OUT_FILE}" + (" with the tuning panel (don't publish this build)" if TUNE else ""))


if __name__ == "__main__":
    if not SHEET_URL:
        sys.exit("SHEET_URL is not set. Add it as a GitHub secret (see README).")
    FEATURES = load_council()
    print(f"{len(FEATURES)} City Council district shapes loaded")
    main()
