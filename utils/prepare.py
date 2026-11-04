"""Raw NYC collision CSV  ->  compact, analysis-ready table.

`transform_raw()` is a pure function (DataFrame in, DataFrame + metadata out)
so it can be unit-tested without touching disk. `scripts/prepare_data.py`
is the command-line wrapper that reads the CSV and writes Parquet.

Design choices (and why)
------------------------
* One row per crash is kept (2M rows, ~20 narrow numeric columns). Every
  dashboard filter is then a fast boolean mask over NumPy arrays, so filters
  affect the map, KPIs and charts *consistently* without pre-aggregating
  every filter combination.
* Contributing factors / vehicle types are stored as **bit masks** (one bit
  per category, set if the category appears in ANY of the five vehicle
  slots). A crash therefore counts once per category: no double counting.
* Missing injury / fatality counts are NOT silently turned into zero. A
  `*_known` flag lets rates use only rows where the outcome is recorded.
* Invalid coordinates become NaN (never replaced by invented locations).
* Missing boroughs stay "Unknown". Optionally they can be *derived* from the
  crash coordinates using an official borough-boundary file (second column
  `borough_filled_code`), and the app keeps the reported borough as default.
"""
from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from utils.schema import (
    BOROUGHS, BOROUGH_NAMES, UNKNOWN_BOROUGH_CODE, NYC_BBOX, MAX_FACTORS,
    OTHER_FACTOR_LABEL, UNSPECIFIED_LABEL, FACTOR_LABEL_FIXES, FACTOR_COLS,
    VEHICLE_COLS, VEHICLE_GROUPS, RAW_REQUIRED_COLS,
)

# ---------------------------------------------------------------------------
# Vehicle-type normalisation
# ---------------------------------------------------------------------------
# The raw vehicle-type field is free text with hundreds of spellings
# ("Sedan", "4 dr sedan", "PASSENGER VEHICLE", "Station Wagon/Sport Utility
# Vehicle", ...). Rules are checked IN ORDER; first match wins.
# These rules are keyword-based and should be reviewed against your data:
# `prepare_data.py` prints the most common raw values and where they landed.
_VEHICLE_RULES: list[tuple[str, str]] = [
    ("Ambulance / Fire / Emergency", r"AMBUL|\bFDNY\b|FIRE ?(TRUCK|ENG|DEPT)?\b|\bEMS\b|EMERG"),
    ("Bicycle / E-bike / E-scooter", r"E[- ]?BIKE|E[- ]?SCOOT|ESCOOT|ELECTRIC (BIKE|SCOOT)"),
    ("Motorcycle / Moped",           r"MOTORCYCLE|MOTORBIKE|MOPED|MINI ?BIKE|DIRT ?BIKE|SCOOTER"),
    ("Bicycle / E-bike / E-scooter", r"\bBIKE\b|BICYC"),
    ("Taxi / For-hire",              r"TAXI|LIVERY|\bUBER\b|\bLYFT\b|FOR[- ]HIRE|LIMO"),
    ("Bus",                          r"\bBUS\b|OMNIBUS|MINI ?BUS"),
    ("Truck / Commercial",           r"TRUCK|TRACTOR|TRAILER|BOX T|DUMP|FLAT ?BED|TANK|CONCRETE|GARBAGE|"
                                     r"REFRIG|STAKE|LARGE COM|SMALL COM|COMMERCIAL|PICK[- ]?UP|\bTOW\b"),
    ("Van",                          r"\bVAN\b|MINIVAN|CARGO"),
    ("SUV / Station wagon",          r"STATION WAGON|SPORT UTILITY|\bSUV\b|WAGON"),
    ("Passenger car / Sedan",        r"SEDAN|PASSENGER|\b[24] ?DR\b|COUPE|CONVERTIBLE|\bCAR\b"),
]
_VEHICLE_RULES_COMPILED = [(VEHICLE_GROUPS.index(g), re.compile(p)) for g, p in _VEHICLE_RULES]
_OTHER_VEHICLE = VEHICLE_GROUPS.index("Other vehicle type")


def classify_vehicle(raw_value: str) -> Optional[int]:
    """Map a raw vehicle-type string to a VEHICLE_GROUPS index (or None if unknown)."""
    s = str(raw_value).strip().upper()
    if s in ("", "UNKNOWN", "UNK", "NAN", "NONE", "NA", "N/A"):
        return None
    for idx, rx in _VEHICLE_RULES_COMPILED:
        if rx.search(s):
            return idx
    return _OTHER_VEHICLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _canonical_factor_map(raw: pd.DataFrame) -> tuple[dict, pd.Series]:
    """Build {raw label -> canonical label | None | UNSPECIFIED_LABEL}.

    * purely numeric entries ("1", "80") are invalid codes -> None
    * case-variants ("Cell Phone (hand-held)" vs "(hand-Held)") are merged
      onto their most common spelling
    * known typos are fixed (FACTOR_LABEL_FIXES)
    """
    counts = pd.Series(dtype="float64")
    for col in FACTOR_COLS:
        counts = counts.add(raw[col].value_counts(), fill_value=0)
    counts = counts.sort_values(ascending=False)

    canon_by_key: dict[str, str] = {}
    mapping: dict = {}
    for label, _n in counts.items():
        stripped = str(label).strip()
        if stripped == "" or re.fullmatch(r"\d+", stripped):
            mapping[label] = None
            continue
        stripped = FACTOR_LABEL_FIXES.get(stripped, stripped)
        key = stripped.casefold()
        canon = canon_by_key.setdefault(key, stripped)
        mapping[label] = canon
    return mapping, counts


def _derive_borough(lat: np.ndarray, lon: np.ndarray, need: np.ndarray,
                    geojson_path: Path) -> Optional[np.ndarray]:
    """Point-in-polygon borough lookup. Returns int8 codes, -1 = not found.

    Requires `shapely>=2` and a borough GeoJSON whose features carry a
    `borough` property (see scripts/prepare_boundaries.py). Only rows flagged
    in `need` are evaluated.
    """
    try:
        import json
        import shapely
        from shapely.geometry import shape
    except ImportError:
        warnings.warn("shapely not installed; skipping borough derivation.")
        return None
    if int(shapely.__version__.split(".")[0]) < 2:
        warnings.warn("shapely>=2 required; skipping borough derivation.")
        return None

    gj = json.loads(Path(geojson_path).read_text())
    out = np.full(len(lat), -1, dtype=np.int8)
    idx = np.flatnonzero(need)
    x, y = lon[idx].astype("float64"), lat[idx].astype("float64")
    for feat in gj["features"]:
        name = str(feat["properties"].get("borough", "")).upper()
        if name not in BOROUGHS:
            continue
        geom = shape(feat["geometry"])
        inside = shapely.contains_xy(geom, x, y)
        out[idx[inside]] = BOROUGHS.index(name)
    return out


# ---------------------------------------------------------------------------
# Main transform
# ---------------------------------------------------------------------------
def transform_raw(raw: pd.DataFrame, boundaries_path: Optional[Path] = None
                  ) -> tuple[pd.DataFrame, dict]:
    """Clean `raw` and return (processed_df, metadata)."""
    missing_cols = [c for c in RAW_REQUIRED_COLS if c not in raw.columns]
    if missing_cols:
        raise ValueError(f"Raw data is missing expected columns: {missing_cols}")

    q: dict = {}                      # data-quality log
    q["rows_raw"] = int(len(raw))

    # 1. duplicates -----------------------------------------------------------
    dup = raw["COLLISION_ID"].duplicated()
    q["duplicate_collision_ids_dropped"] = int(dup.sum())
    raw = raw.loc[~dup].reset_index(drop=True)

    # 2. dates / time ---------------------------------------------------------
    date = pd.to_datetime(raw["CRASH DATE"], format="%m/%d/%Y", errors="coerce")
    bad_date = date.isna()
    if bad_date.mean() > 0.05:
        raise ValueError(
            "More than 5% of CRASH DATE values failed to parse with the format "
            "%m/%d/%Y. Check the date format of your CSV.")
    q["rows_dropped_bad_date"] = int(bad_date.sum())
    raw = raw.loc[~bad_date].reset_index(drop=True)
    date = date.loc[~bad_date].reset_index(drop=True)

    hour = _num(raw["CRASH TIME"].astype(str).str.split(":").str[0])
    hour = hour.where((hour >= 0) & (hour <= 23))
    q["rows_unparseable_time"] = int(hour.isna().sum())
    hour = hour.fillna(-1).astype("int8")

    year = date.dt.year.astype("int16")
    month = date.dt.month.astype("int8")
    n = len(raw)

    # 3. borough --------------------------------------------------------------
    b = raw["BOROUGH"].astype("string").str.strip().str.upper()
    borough_code = np.full(n, UNKNOWN_BOROUGH_CODE, dtype="int8")
    for i, name in enumerate(BOROUGHS):
        borough_code[(b == name).fillna(False).to_numpy(dtype=bool)] = i
    q["borough_missing_or_unrecognised"] = int((borough_code == UNKNOWN_BOROUGH_CODE).sum())
    q["borough_missing_pct"] = round(100 * q["borough_missing_or_unrecognised"] / n, 2)
    q["borough_missing_pct_by_year"] = {
        int(y): round(100 * float(m), 1)
        for y, m in pd.Series(borough_code == UNKNOWN_BOROUGH_CODE).groupby(year.to_numpy()).mean().items()
    }

    # 4. coordinates ----------------------------------------------------------
    lat_raw, lon_raw = _num(raw["LATITUDE"]), _num(raw["LONGITUDE"])
    has_any = lat_raw.notna() & lon_raw.notna()
    la0, la1, lo0, lo1 = NYC_BBOX
    valid = has_any & lat_raw.between(la0, la1) & lon_raw.between(lo0, lo1)
    q["coords_missing"] = int((~has_any).sum())
    q["coords_present_but_invalid"] = int((has_any & ~valid).sum())
    q["coords_valid"] = int(valid.sum())
    q["coords_valid_pct"] = round(100 * q["coords_valid"] / n, 2)
    lat = lat_raw.where(valid).astype("float32").to_numpy()
    lon = lon_raw.where(valid).astype("float32").to_numpy()

    # optional: derive borough from coordinates
    filled_code = borough_code.copy()
    has_filled = False
    if boundaries_path and Path(boundaries_path).exists():
        need = (borough_code == UNKNOWN_BOROUGH_CODE) & valid.to_numpy()
        derived = _derive_borough(lat, lon, need, Path(boundaries_path))
        if derived is not None:
            got = need & (derived >= 0)
            filled_code[got] = derived[got]
            has_filled = True
            q["borough_derived_from_coords"] = int(got.sum())
            # agreement check on rows that already have a reported borough
            rep = np.flatnonzero((borough_code != UNKNOWN_BOROUGH_CODE) & valid.to_numpy())
            if len(rep):
                rng = np.random.default_rng(0)
                samp = rng.choice(rep, size=min(100_000, len(rep)), replace=False)
                mask_s = np.zeros(n, bool); mask_s[samp] = True
                chk = _derive_borough(lat, lon, mask_s, Path(boundaries_path))
                ok = chk[samp] == borough_code[samp]
                q["borough_reported_vs_derived_agreement_pct"] = round(100 * float(ok.mean()), 2)

    # 5. injury / fatality ----------------------------------------------------
    inj_raw = _num(raw["NUMBER OF PERSONS INJURED"])
    kil_raw = _num(raw["NUMBER OF PERSONS KILLED"])
    inj_known = inj_raw.notna().to_numpy()
    kil_known = kil_raw.notna().to_numpy()
    q["persons_injured_missing"] = int((~inj_known).sum())
    q["persons_killed_missing"] = int((~kil_known).sum())
    injured = inj_raw.fillna(0).clip(lower=0).astype("int16").to_numpy()
    killed = kil_raw.fillna(0).clip(lower=0).astype("int8").to_numpy()

    def _small(col, dtype):
        return _num(raw[col]).fillna(0).clip(lower=0).astype(dtype).to_numpy()

    # 6. contributing factors -------------------------------------------------
    fmap, fcounts = _canonical_factor_map(raw)
    tokens = {}
    for col in FACTOR_COLS:
        tokens[col] = raw[col].map(fmap)                     # NaN stays NaN
    canon_counts: dict[str, float] = {}
    for label, c in fcounts.items():
        canon = fmap.get(label)
        if canon is None:
            continue
        canon_counts[canon] = canon_counts.get(canon, 0) + float(c)
    unspec_key = UNSPECIFIED_LABEL.casefold()
    usable = {k: v for k, v in canon_counts.items() if k.casefold() != unspec_key}
    ordered = sorted(usable, key=lambda k: -usable[k])
    if len(ordered) > MAX_FACTORS:
        keep = ordered[:MAX_FACTORS - 1]
        rare = set(ordered[MAX_FACTORS - 1:])
        ordered = keep + [OTHER_FACTOR_LABEL]
        for col in FACTOR_COLS:
            tokens[col] = tokens[col].where(~tokens[col].isin(rare), OTHER_FACTOR_LABEL)
        q["factor_labels_merged_into_other"] = len(rare)
    factor_index = {name: i for i, name in enumerate(ordered)}

    factor_mask = np.zeros(n, dtype=np.uint64)
    factor1 = np.full(n, -1, dtype="int8")
    for slot, col in enumerate(FACTOR_COLS):
        idx = tokens[col].map(factor_index).astype("float64").to_numpy()
        ok = ~np.isnan(idx)
        bits = np.left_shift(np.uint64(1), idx[ok].astype(np.uint64))
        factor_mask[ok] |= bits
        if slot == 0:
            factor1[ok] = idx[ok].astype("int8")
    q["factor1_usable_pct"] = round(100 * float((factor1 >= 0).mean()), 2)
    q["factor1_unspecified_or_missing_pct"] = round(100 - q["factor1_usable_pct"], 2)
    q["factor_numeric_junk_labels"] = int(sum(1 for v in fmap.values() if v is None))
    q["n_factor_categories"] = len(ordered)

    # 7. vehicle types --------------------------------------------------------
    veh_mask = np.zeros(n, dtype=np.uint16)
    raw_vehicle_counts = pd.Series(dtype="float64")
    for col in VEHICLE_COLS:
        s = raw[col]
        raw_vehicle_counts = raw_vehicle_counts.add(s.value_counts(), fill_value=0)
        uniq = s.dropna().unique()
        vmap = {u: classify_vehicle(u) for u in uniq}
        codes = s.map(vmap).astype("float64").to_numpy()
        ok = ~np.isnan(codes)
        veh_mask[ok] |= np.left_shift(np.uint16(1), codes[ok].astype(np.uint16))
    raw_vehicle_counts = raw_vehicle_counts.sort_values(ascending=False)
    audit = []
    for label, c in raw_vehicle_counts.head(40).items():
        g = classify_vehicle(label)
        audit.append({"raw": str(label), "count": int(c),
                      "group": VEHICLE_GROUPS[g] if g is not None else "(unknown - no group)"})
    in_other = sum(c for lbl, c in raw_vehicle_counts.items()
                   if classify_vehicle(lbl) == _OTHER_VEHICLE)
    q["vehicle_other_group_share_pct"] = round(
        100 * float(in_other) / max(float(raw_vehicle_counts.sum()), 1.0), 2)
    q["vehicle_any_group_pct"] = round(100 * float((veh_mask != 0).mean()), 2)

    # 8. assemble -------------------------------------------------------------
    out = pd.DataFrame({
        "collision_id": raw["COLLISION_ID"].astype("int64").to_numpy(),
        "year": year.to_numpy(),
        "month": month.to_numpy(),
        "ym": (year.astype("int32") * 12 + month.astype("int32") - 1).astype("int32").to_numpy(),
        "dow": date.dt.dayofweek.astype("int8").to_numpy(),
        "hour": hour.to_numpy(),
        "borough_code": borough_code,
        "borough_filled_code": filled_code,
        "lat": lat,
        "lon": lon,
        "injured": injured,
        "killed": killed,
        "inj_known": inj_known,
        "kill_known": kil_known,
        "any_injury": inj_known & (injured > 0),
        "any_fatality": kil_known & (killed > 0),
        "ped_inj": _small("NUMBER OF PEDESTRIANS INJURED", "int16"),
        "cyc_inj": _small("NUMBER OF CYCLIST INJURED", "int16"),
        "mot_inj": _small("NUMBER OF MOTORIST INJURED", "int16"),
        "ped_kill": _small("NUMBER OF PEDESTRIANS KILLED", "int8"),
        "cyc_kill": _small("NUMBER OF CYCLIST KILLED", "int8"),
        "mot_kill": _small("NUMBER OF MOTORIST KILLED", "int8"),
        "factor1": factor1,
        "factor_mask": factor_mask,
        "veh_mask": veh_mask,
    })
    out["collision_id"] = out["collision_id"].astype("int32")

    # 9. coverage / partial years --------------------------------------------
    dmin, dmax = date.min(), date.max()
    months_per_year = out.groupby("year")["month"].nunique()
    partial = {int(y) for y, m in months_per_year.items() if m < 12}
    if (dmin.month, dmin.day) != (1, 1):
        partial.add(int(dmin.year))
    if (dmax.month, dmax.day) != (12, 31):
        partial.add(int(dmax.year))
    q["rows_final"] = int(n)
    q["crashes_per_year"] = {int(y): int(c) for y, c in out["year"].value_counts().sort_index().items()}

    meta = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date_min": dmin.strftime("%Y-%m-%d"),
        "date_max": dmax.strftime("%Y-%m-%d"),
        "years": sorted(int(y) for y in out["year"].unique()),
        "partial_years": sorted(partial),
        "boroughs": BOROUGH_NAMES,
        "has_filled_borough": has_filled,
        "factors": ordered,
        "vehicle_groups": VEHICLE_GROUPS,
        "quality": q,
        "vehicle_audit_top40": audit,
    }
    return out, meta
