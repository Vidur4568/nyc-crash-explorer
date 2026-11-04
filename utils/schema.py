"""Shared constants used by the data-prep pipeline and the Streamlit app.

Nothing here depends on Streamlit, so it can be imported from anywhere.
"""

# --- Boroughs -------------------------------------------------------------
BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
UNKNOWN_BOROUGH = "Unknown"
BOROUGH_NAMES = BOROUGHS + [UNKNOWN_BOROUGH]          # index = stored code
UNKNOWN_BOROUGH_CODE = len(BOROUGHS)                  # 5


def borough_label(name: str) -> str:
    """'STATEN ISLAND' -> 'Staten Island' (leaves 'Unknown' alone)."""
    return name.title() if name != UNKNOWN_BOROUGH else name


# --- Time ------------------------------------------------------------------
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]            # index = pandas dayofweek

# --- Geography -------------------------------------------------------------
# Generous bounding box around NYC (lat_min, lat_max, lon_min, lon_max).
# Anything outside (including the (0, 0) placeholder coordinates present in
# the raw file) is treated as an invalid location. It is a rectangle, so it
# still contains some water / New Jersey / Nassau County; it only removes
# obviously wrong coordinates.
NYC_BBOX = (40.45, 40.95, -74.30, -73.65)

# Origin for the analysis grid. Cells are squares of `size_m` metres.
GRID_LAT0 = 40.40
GRID_LON0 = -74.30
GRID_REF_LAT = 40.72                 # latitude used to convert metres -> degrees lon
METRES_PER_DEG_LAT = 111_320.0

# Approximate camera presets (centre lat, centre lon, zoom). These are map
# view settings, not data values.
CITY_VIEW = (40.7128, -73.9560, 9.9)
BOROUGH_VIEW = {
    "BRONX": (40.8448, -73.8648, 11.4),
    "BROOKLYN": (40.6501, -73.9496, 11.2),
    "MANHATTAN": (40.7831, -73.9712, 11.3),
    "QUEENS": (40.7282, -73.7949, 10.8),
    "STATEN ISLAND": (40.5795, -74.1502, 11.3),
}

# --- Contributing factors / vehicles ---------------------------------------
MAX_FACTORS = 63                       # one bit each in a uint64 (bit 63 unused)
OTHER_FACTOR_LABEL = "Other (rare codes)"
UNSPECIFIED_LABEL = "Unspecified"
# Known typos / spelling issues in the source data -> corrected label.
FACTOR_LABEL_FIXES = {"Illnes": "Illness"}

FACTOR_COLS = [f"CONTRIBUTING FACTOR VEHICLE {i}" for i in range(1, 6)]
VEHICLE_COLS = [f"VEHICLE TYPE CODE {i}" for i in range(1, 6)]

# Normalised vehicle groups (index = bit position in `veh_mask`).
VEHICLE_GROUPS = [
    "Passenger car / Sedan",
    "SUV / Station wagon",
    "Taxi / For-hire",
    "Van",
    "Truck / Commercial",
    "Bus",
    "Motorcycle / Moped",
    "Bicycle / E-bike / E-scooter",
    "Ambulance / Fire / Emergency",
    "Other vehicle type",
]

RAW_REQUIRED_COLS = (
    ["CRASH DATE", "CRASH TIME", "BOROUGH", "LATITUDE", "LONGITUDE",
     "NUMBER OF PERSONS INJURED", "NUMBER OF PERSONS KILLED",
     "NUMBER OF PEDESTRIANS INJURED", "NUMBER OF PEDESTRIANS KILLED",
     "NUMBER OF CYCLIST INJURED", "NUMBER OF CYCLIST KILLED",
     "NUMBER OF MOTORIST INJURED", "NUMBER OF MOTORIST KILLED",
     "COLLISION_ID"] + FACTOR_COLS + VEHICLE_COLS
)
