# ===== SETTINGS: everything you might want to edit lives in this cell =====

# --- Your Google Sheet (shared as "Anyone with the link: Viewer") ---
# The link itself is not kept here because this repo is public. The GitHub Action reads it from the
# SHEET_URL secret; on your own computer, run  export SHEET_URL='...'  before build_map.py.
SHEET_TAB = "Council"     # name of the tab that holds the district rows

# --- On load ---
DEFAULT_BILL = 0          # bill selected at start: 0, 1 or 2 (position in BILLS below), or None for no bill
SHOW_NUMBERS = True       # show district numbers on the map at start

# --- Basemap: "carto" (light grey), "esri" (light grey), or "none" (no tiles; most reliable) ---
BASEMAP = "none"

# --- Sheet column headers (capitalization and extra spaces don't matter, the wording does) ---
COLS = dict(
    district="District",
    rep="Representative",
    party="Party",
    budget="Committed to budget line item",
    bnt="Budget Negotiation Team (2025-26)",
    sio="SIO",
    pc="Progressive Caucus",
    notes="Notes",
)
# (Sheet column header, label shown on the map)
BILLS = [
    ("CURB Act (Int 0796)",              "CURB Act"),
    ("DCS Bill (Int 0778)",              "DCS Bill"),
    ("Abolish Gang Database (Int 0464)", "Abolish Gang Database"),
]
COMMITTEES = [
    ("Criminal Justice Committee", "Criminal Justice"),
    ("Public Safety Committee",    "Public Safety"),
    ("General Welfare Committee",  "General Welfare"),
]

# --- Bill support values: (value in the Sheet, label on the map, fill color). Top to bottom in the legend. ---
STATUSES = [
    ("cosponsor",       "Cosponsor",       "#1a7f37"),
    ("leaning support", "Leaning support", "#91cf60"),
    ("undecided",       "Undecided",       "#fee08b"),
    ("leaning oppose",  "Leaning oppose",  "#fc8d59"),
    ("oppose",          "Oppose",          "#d73027"),
]
NO_DATA_COLOR = "#ffffff"        # bill cell is blank or unrecognized
NEUTRAL_FILL = "#ffffff"         # fill when no bill (or budget) layer is colouring a district
BASE_OUTLINE_COLOR = "#555555"   # thin district borders
BUDGET_COLOR = STATUSES[0][2]    # "Committed to budget line item" fill (defaults to the Cosponsor color)
FILL_OPACITY = 0.8

# --- Hatching. angle: 45 = "/" diagonal, -45 = "\" diagonal. spacing/width are in pixels. ---
COMMITTEE_HATCH = dict(color="#1b2a6b", angle=45,  spacing=7, width=2)
BNT_HATCH       = dict(color="#7b1fa2", angle=-45, spacing=7, width=2)

# --- Outlines (weight in pixels). If a district has both, SIO is drawn wide with the Progressive Caucus line inside it. ---
SIO_OUTLINE = dict(color="#006400", weight=3)    # dark green
PC_OUTLINE  = dict(color="#8fe388", weight=3)    # light green

# --- What counts as "checked" in the binary columns (checkbox cells export as TRUE/FALSE) ---
FALSE_VALUES = {"false"}   # anything else counts as checked
YES_VALUES = {"true"}                                 # shown as "Yes" in the info box

# --- Text labels ---
LABELS = dict(
    billHeading="Bill support",
    budgetHeading="Budget",
    committeeHeading="City Council committees",
    otherHeading="Other",
    none="None",
    noData="No data",
    noRep="Representative not entered",
    district="District",
    party="Party",
    budget="Committed to budget line item",
    bnt="Budget Negotiation Team (2025-26)",
    sio="SIO",
    pc="Progressive Caucus",
    notes="Notes",
    yes="Yes",
    no="No",
    showNumbers="Show district numbers",
)

# --- Heatmap settings ---

HEAT_SHOW_AT_START = False
HEAT_HEADING = "QoL misdemeanor arrests heatmap"
HEAT_LABEL = ""
HEAT_RADIUS = 12
HEAT_BLUR = 20
HEAT_MAX = 0.15
HEAT_MIN_OPACITY = 0.25
HEAT_MAX_ZOOM = 15
HEAT_PERCENTILE = 90
HEAT_GRADIENT = {0.2: "#fcfdbf", 0.4: "#fc8961", 0.6: "#b73779", 0.8: "#51127c", 1.0: "#000004"}

# --- B HEARD precincts (NYPD precinct outlines drawn over the council districts) ---
BHEARD_SHOW_AT_START = False
BHEARD_HEADING = "B HEARD"
BHEARD_LABEL = "B HEARD precincts"
NYPD_PRECINCT_FILE = "data/police_precincts.geojson"   # optional local copy; downloaded from NYC Open Data if missing
BHEARD_PRECINCTS = [
    40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 52,
    25, 26, 28, 30, 32, 33, 34,
    63, 69, 67, 71, 73, 75,
    104, 108, 110, 112, 114, 115
]
BHEARD_STYLE = dict(color="#00008B", weight=2.5, fillOpacity=0.2)

# --- Encampment sweeps (district shading, read from the DHS LL34 reports in DHS_SWEEPS_FOLDER) ---
SWEEPS_SHOW_AT_START = False
SWEEPS_HEADING = "Encampment sweeps"
SWEEPS_LABEL = "DHS encampment sweeps"
DHS_SWEEPS_FOLDER = "data/dhs_sweeps/"   # drop each quarter's .xlsx from the DHS stats page in here
SWEEPS_METRIC = "sweeps"    # "sweeps" = number of sweeps, "people" = people affected
SWEEPS_PERCENTILE = 90      # districts at or above this percentile get the darkest shade
SWEEPS_COLOR = "#BB1F00"
SWEEPS_OPACITY = 0.85

# --- Majority-minority districts (council districts under 50% non-Hispanic white, 2020 Census via NYC Planning) ---
MAJMIN_SHOW_AT_START = False
MAJMIN_HEADING = "Demographics"
MAJMIN_LABEL = "Majority-minority districts"
MAJMIN_DOTS = dict(color="#3d2b1f", spacing=8, radius=1.6)   # dot pattern; spacing and radius in pixels
CENSUS_FILE = "data/nyc_decennialcensusdata_2010_2020_change-core-geographies.xlsx"   # optional local copy; downloaded if missing

COUNCIL_FILE = "data/council.geojson"   # optional local copy; downloaded from NYC Open Data if missing