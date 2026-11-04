"""SYNTHETIC test fixture. NOT REAL DATA - never use for findings.

Generates a DataFrame with the same columns as the NYC crash CSV and with the
same kinds of defects that the real file has (missing boroughs, (0,0) and
out-of-range coordinates, numeric junk in factor columns, case-variant
labels, the 'Illnes' typo, missing injury counts, duplicate ids, a partial
first and last year). It exists only so the pipeline can be tested without
the 2M-row CSV.
"""
import numpy as np
import pandas as pd

from utils.schema import FACTOR_COLS, VEHICLE_COLS

FACTORS = [
    "Unspecified", "Driver Inattention/Distraction", "Failure to Yield Right-of-Way",
    "Unsafe Speed", "Following Too Closely", "Illnes", "Cell Phone (hand-held)",
    "Cell Phone (hand-Held)", "Traffic Control Disregarded", "Backing Unsafely",
    "1", "80",
]
FACTOR_P = np.array([30, 25, 8, 6, 7, 1, 1, 1, 4, 5, 0.5, 0.5], dtype=float)
FACTOR_P /= FACTOR_P.sum()

VEHICLES = [
    "Sedan", "SEDAN", "4 dr sedan", "Station Wagon/Sport Utility Vehicle", "Taxi",
    "Bike", "E-Bike", "E-Scooter", "Box Truck", "PICK-UP TRUCK", "Bus", "Motorcycle",
    "Ambulance", "UNKNOWN", "Tractor Truck Diesel", "Van", "Town Car", "Dirt Bike",
    "Moped", "Fire Truck", "Livery Vehicle", "Chassis Cab",
]


def make_raw(n: int = 40_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    days = pd.date_range("2012-07-01", "2025-06-03")
    date = rng.choice(days, size=n)
    date_s = pd.to_datetime(date).strftime("%m/%d/%Y")
    hh = rng.integers(0, 24, n)
    mm = rng.integers(0, 60, n)
    time_s = np.array([f"{h}:{m:02d}" for h, m in zip(hh, mm)], dtype=object)
    time_s[rng.random(n) < 0.002] = "bad"

    boro = rng.choice(["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"],
                      size=n, p=[.15, .30, .22, .26, .07]).astype(object)
    boro[rng.random(n) < 0.30] = np.nan
    boro[rng.random(n) < 0.01] = " brooklyn "          # whitespace / case noise

    lat = rng.uniform(40.50, 40.90, n)
    lon = rng.uniform(-74.20, -73.70, n)
    # make crashes cluster so hotspots exist
    clustered = rng.random(n) < 0.4
    lat[clustered] = rng.normal(40.7580, 0.01, clustered.sum())
    lon[clustered] = rng.normal(-73.9855, 0.01, clustered.sum())
    r = rng.random(n)
    lat = lat.astype(object); lon = lon.astype(object)
    lat[r < 0.10] = np.nan; lon[r < 0.10] = np.nan
    z = (r >= 0.10) & (r < 0.13)
    lat[z] = 0.0; lon[z] = 0.0
    bad = (r >= 0.13) & (r < 0.14)
    lon[bad] = -201.36

    inj = rng.poisson(0.32, n).astype(float)
    inj[rng.random(n) < 0.002] = np.nan
    kil = (rng.random(n) < 0.0015).astype(float)
    kil[rng.random(n) < 0.002] = np.nan

    df = pd.DataFrame({
        "CRASH DATE": date_s, "CRASH TIME": time_s, "BOROUGH": boro,
        "LATITUDE": pd.to_numeric(pd.Series(lat), errors="coerce"),
        "LONGITUDE": pd.to_numeric(pd.Series(lon), errors="coerce"),
        "NUMBER OF PERSONS INJURED": inj, "NUMBER OF PERSONS KILLED": kil,
        "NUMBER OF PEDESTRIANS INJURED": rng.poisson(0.06, n),
        "NUMBER OF PEDESTRIANS KILLED": 0,
        "NUMBER OF CYCLIST INJURED": rng.poisson(0.03, n),
        "NUMBER OF CYCLIST KILLED": 0,
        "NUMBER OF MOTORIST INJURED": rng.poisson(0.2, n),
        "NUMBER OF MOTORIST KILLED": 0,
        "COLLISION_ID": np.arange(3_000_000, 3_000_000 + n),
    })
    # make injuries somewhat dependent on factor so rates differ by factor
    for i, col in enumerate(FACTOR_COLS):
        vals = rng.choice(FACTORS, size=n, p=FACTOR_P).astype(object)
        vals[rng.random(n) < (0.003 if i == 0 else 0.16 if i == 1 else 0.93 + 0.01 * i)] = np.nan
        df[col] = vals
    for i, col in enumerate(VEHICLE_COLS):
        vals = rng.choice(VEHICLES, size=n).astype(object)
        vals[rng.random(n) < (0.01 if i == 0 else 0.2 if i == 1 else 0.93 + 0.01 * i)] = np.nan
        df[col] = vals

    unsafe = df[FACTOR_COLS[0]] == "Unsafe Speed"
    df.loc[unsafe & (rng.random(n) < 0.5), "NUMBER OF PERSONS INJURED"] += 1

    # duplicates (same COLLISION_ID repeated) - must be dropped
    dups = df.sample(25, random_state=1).copy()
    return pd.concat([df, dups], ignore_index=True)
