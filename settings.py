# ===== SETTINGS: edit colors, labels and column names here (then commit; the map rebuilds itself) =====

# --- Your Google Sheet ---
# The Sheet link is NOT stored here. It lives in a GitHub secret named SHEET_URL (see README).
SHEET_TAB = "Council"     # name of the tab that holds the district rows

# --- Map text ---
MAP_TITLE = "City Council Support Map"
SUBTITLE = "Click a district for details."

# --- On load ---
DEFAULT_BILL = 0          # bill selected at start: 0, 1 or 2 (position in BILLS below), or None for no bill
SHOW_NUMBERS = True       # show district numbers on the map at start

# --- Basemap: "carto" (light grey), "esri" (light grey), or "none" (no tiles; most reliable) ---
BASEMAP = "carto"
BASEMAPS = {
    "carto": ("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
              "&copy; OpenStreetMap contributors &copy; CARTO", {}),
    "esri": ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
             "Tiles &copy; Esri", {"max_native_zoom": 16}),
}

# --- Sheet column headers (capitalization and extra spaces don't matter, the wording does) ---
COLS = dict(
    district="District",
    rep="Representative",
    party="Party",
    budget="Committed to budget line item",
    bnt="Budget Negotiation Team (2025-26)",
    sio="SIO",
    pc="Progressive Caucus Position",
    notes="Notes",
)
# (Sheet column header, label shown on the map)
BILLS = [
    ("CURB Act (Int 1176)",              "CURB Act (Int 1176)"),
    ("DCS Bill (Int 0778)",              "DCS Bill (Int 0778)"),
    ("Abolish Gang Database (Int 0464)", "Abolish Gang Database (Int 0464)"),
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
NO_DATA_COLOR = "#d9d9d9"        # bill cell is blank or unrecognized
NEUTRAL_FILL = "#f4f4f4"         # fill when no bill (or budget) layer is colouring a district
BASE_OUTLINE_COLOR = "#555555"   # thin district borders
BUDGET_COLOR = STATUSES[0][2]    # "Committed to budget line item" fill (defaults to the Cosponsor color)
FILL_OPACITY = 0.8

# --- Hatching. angle: 45 = "/" diagonal, -45 = "\" diagonal. spacing/width are in pixels. ---
COMMITTEE_HATCH = dict(color="#1b2a6b", angle=45,  spacing=7, width=2)
BNT_HATCH       = dict(color="#7b1fa2", angle=-45, spacing=7, width=2)

# --- Outlines (weight in pixels). If a district has both, SIO is drawn wide with the Progressive Caucus line inside it. ---
SIO_OUTLINE = dict(color="#006400", weight=6)    # dark green
PC_OUTLINE  = dict(color="#8fe388", weight=3)    # light green

# --- What counts as "checked" in the binary columns (checkbox cells export as TRUE/FALSE) ---
FALSE_VALUES = {"", "false", "no", "n", "0", "none", "-", "n/a", "na", "unchecked"}   # anything else counts as checked
YES_VALUES = {"true", "yes", "y", "x", "1", "checked"}                                 # shown as "Yes" in the info box

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
