"""Tests for the data pipeline and analytics engine.

Run:   python tests/test_pipeline.py        (or: pytest -q)

IMPORTANT: these run on SYNTHETIC data (tests/make_synthetic_data.py).
They prove the code is internally consistent and agrees with a plain-pandas
re-computation; they say nothing about the real NYC numbers.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.make_synthetic_data import make_raw                      # noqa: E402
from utils import data_helpers as dh                                 # noqa: E402
from utils.prepare import transform_raw, classify_vehicle            # noqa: E402
from utils.schema import FACTOR_COLS, VEHICLE_COLS, VEHICLE_GROUPS, BOROUGH_NAMES  # noqa: E402

RAW = make_raw()
PROC, META = transform_raw(RAW)
D = dh.CrashData(PROC, META)

# oracle frame: deduplicated raw data, notebook-style columns --------------------
ORA = RAW.drop_duplicates("COLLISION_ID").reset_index(drop=True).copy()
ORA["DATE"] = pd.to_datetime(ORA["CRASH DATE"], format="%m/%d/%Y")
ORA["YEAR"] = ORA["DATE"].dt.year
ORA["HOUR"] = pd.to_numeric(ORA["CRASH TIME"].str.split(":").str[0], errors="coerce")
ORA["BOROUGH"] = ORA["BOROUGH"].str.strip().str.upper()
INJ_KNOWN = ORA["NUMBER OF PERSONS INJURED"].notna()
ORA["ANY_INJURY"] = ORA["NUMBER OF PERSONS INJURED"] > 0           # NaN -> False


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(b))


def test_dedup_and_row_counts():
    assert META["quality"]["duplicate_collision_ids_dropped"] == len(RAW) - len(ORA)
    assert len(PROC) == len(ORA) - META["quality"]["rows_dropped_bad_date"]
    assert PROC["collision_id"].is_unique


def test_partial_years_detected():
    assert META["date_min"].startswith("2012-0")
    assert 2012 in META["partial_years"] and 2025 in META["partial_years"]
    assert 2018 not in META["partial_years"]


def test_invalid_coordinates_removed():
    lat = PROC["lat"].to_numpy()
    lon = PROC["lon"].to_numpy()
    ok = np.isfinite(lat)
    assert (lat[ok] > 40.45).all() and (lat[ok] < 40.95).all()
    assert (lon[ok] > -74.30).all() and (lon[ok] < -73.65).all()
    q = META["quality"]
    assert q["coords_present_but_invalid"] > 0            # (0,0) and -201 rows exist
    assert q["coords_valid"] == int(ok.sum())
    assert (np.isnan(lat) == np.isnan(lon)).all()


def test_missing_injury_not_treated_as_zero():
    miss = ~PROC["inj_known"].to_numpy()
    assert miss.sum() == META["quality"]["persons_injured_missing"] > 0
    assert not PROC["any_injury"].to_numpy()[miss].any()
    mask = np.ones(D.n, bool)
    k = dh.kpis(D, mask, mask)
    expected = 100 * ORA["ANY_INJURY"][INJ_KNOWN].mean()
    assert approx(k["injury_pct"], expected, 1e-6)           # denominator excludes unknown
    naive = 100 * ORA["ANY_INJURY"].mean()                   # notebook way (NaN counted as 0)
    assert naive != k["injury_pct"]


def test_factor_labels_cleaned():
    f = META["factors"]
    assert "Illness" in f and "Illnes" not in f
    assert not any(x.isdigit() for x in f)                  # '1', '80' removed
    assert "Unspecified" not in f
    cell = [x for x in f if x.casefold().startswith("cell phone")]
    assert len(cell) == 1                                    # case variants merged


def test_vehicle_classifier():
    cases = {
        "Sedan": "Passenger car / Sedan", "4 dr sedan": "Passenger car / Sedan",
        "Station Wagon/Sport Utility Vehicle": "SUV / Station wagon",
        "Taxi": "Taxi / For-hire", "Town Car": "Passenger car / Sedan",
        "Tow Truck": "Truck / Commercial", "School Bus": "Bus",
        "Bike": "Bicycle / E-bike / E-scooter", "E-Bike": "Bicycle / E-bike / E-scooter",
        "E-Scooter": "Bicycle / E-bike / E-scooter", "Dirt Bike": "Motorcycle / Moped",
        "Moped": "Motorcycle / Moped", "Motorcycle": "Motorcycle / Moped",
        "Box Truck": "Truck / Commercial", "PICK-UP TRUCK": "Truck / Commercial",
        "Bus": "Bus", "Van": "Van", "Ambulance": "Ambulance / Fire / Emergency",
        "Fire Truck": "Ambulance / Fire / Emergency",
        "Livery Vehicle": "Taxi / For-hire", "Chassis Cab": "Other vehicle type",
    }
    for raw, grp in cases.items():
        got = classify_vehicle(raw)
        assert got is not None and VEHICLE_GROUPS[got] == grp, (raw, got)
    assert classify_vehicle("UNKNOWN") is None
    assert classify_vehicle(np.nan) is None


def test_borough_and_year_tables_reconcile():
    f = dh.Filters(year_range=(2012, 2025))
    m = dh.build_mask(D, f)
    assert m.sum() == D.n
    b = dh.by_borough(D, m)
    assert b["crashes"].sum() == m.sum()                      # includes Unknown row
    assert list(b["borough"]) == BOROUGH_NAMES
    y = dh.by_year(D, m)
    assert y["crashes"].sum() == m.sum()
    mo = dh.by_month(D, m)
    assert mo["crashes"].sum() == m.sum()
    h = dh.by_hour(D, m)
    assert h["crashes"].sum() == (D.hour >= 0).sum()
    dhm = dh.dow_hour(D, m)
    assert dhm["crashes"].sum() == (D.hour >= 0).sum()


def test_borough_injury_rate_matches_notebook_method():
    m = dh.build_mask(D, dh.Filters(year_range=(2012, 2025)))
    b = dh.by_borough(D, m).set_index("borough")
    for name in ["BROOKLYN", "QUEENS"]:
        sub = ORA[ORA["BOROUGH"] == name]
        kn = sub["NUMBER OF PERSONS INJURED"].notna()
        assert b.loc[name, "crashes"] == len(sub)
        assert b.loc[name, "injury_crashes"] == sub["ANY_INJURY"].sum()
        assert approx(b.loc[name, "injury_rate"], 100 * sub["ANY_INJURY"][kn].mean(), 1e-9)


def test_year_and_borough_filter_kpis_vs_pandas():
    f = dh.Filters(boroughs=("BROOKLYN",), year_range=(2014, 2019))
    m = dh.build_mask(D, f)
    sub = ORA[(ORA["BOROUGH"] == "BROOKLYN") & ORA["YEAR"].between(2014, 2019)]
    k = dh.kpis(D, m, m)
    assert k["crashes"] == len(sub)
    assert k["persons_injured"] == int(sub["NUMBER OF PERSONS INJURED"].fillna(0).sum())
    kn = sub["NUMBER OF PERSONS INJURED"].notna()
    assert approx(k["injury_pct"], 100 * sub["ANY_INJURY"][kn].mean(), 1e-9)


def test_hour_filter_and_dow_filter():
    f = dh.Filters(year_range=(2012, 2025), hour_range=(7, 9), days=(5, 6))
    m = dh.build_mask(D, f)
    sub = ORA[ORA["HOUR"].between(7, 9) & ORA["DATE"].dt.dayofweek.isin([5, 6])]
    assert m.sum() == len(sub)


def test_factor_vehicle1_matches_pandas():
    m = dh.build_mask(D, dh.Filters(year_range=(2012, 2025)))
    t = dh.factor_table(D, m, "vehicle1").set_index("factor")
    for fac in ["Unsafe Speed", "Driver Inattention/Distraction"]:
        sub = ORA[ORA[FACTOR_COLS[0]] == fac]
        kn = sub["NUMBER OF PERSONS INJURED"].notna()
        assert t.loc[fac, "crashes"] == len(sub)
        assert approx(t.loc[fac, "injury_rate"], 100 * sub["ANY_INJURY"][kn].mean(), 1e-9)
    # merged spelling variants: counts equal the sum of both spellings
    both = ORA[FACTOR_COLS[0]].isin(["Cell Phone (hand-held)", "Cell Phone (hand-Held)"]).sum()
    cell = [x for x in t.index if x.casefold().startswith("cell phone")][0]
    assert t.loc[cell, "crashes"] == both


def test_factor_any_scope_counts_each_crash_once():
    f = dh.Filters(year_range=(2012, 2025), factors=("Unsafe Speed",), factor_scope="any")
    m = dh.build_mask(D, f)
    any_hit = (ORA[FACTOR_COLS] == "Unsafe Speed").any(axis=1)
    assert m.sum() == any_hit.sum()                          # once per crash, not per vehicle
    n_cells = (ORA[FACTOR_COLS] == "Unsafe Speed").sum().sum()
    assert n_cells > any_hit.sum()                           # fixture does contain multi-vehicle repeats
    t = dh.factor_table(D, dh.build_mask(D, dh.Filters(year_range=(2012, 2025))), "any").set_index("factor")
    assert t.loc["Unsafe Speed", "crashes"] == any_hit.sum()


def test_factor_vehicle1_filter():
    f = dh.Filters(year_range=(2012, 2025), factors=("Unsafe Speed",), factor_scope="vehicle1")
    m = dh.build_mask(D, f)
    assert m.sum() == (ORA[FACTOR_COLS[0]] == "Unsafe Speed").sum()


def test_vehicle_filter_and_table():
    grp = "Bicycle / E-bike / E-scooter"
    f = dh.Filters(year_range=(2012, 2025), vehicles=(grp,))
    m = dh.build_mask(D, f)
    bike = ORA[VEHICLE_COLS].apply(lambda s: s.isin(["Bike", "E-Bike", "E-Scooter"])).any(axis=1)
    assert m.sum() == bike.sum()
    t = dh.vehicle_table(D, dh.build_mask(D, dh.Filters(year_range=(2012, 2025)))).set_index("vehicle_group")
    assert t.loc[grp, "crashes"] == bike.sum()


def test_severity_filter_and_kpi_rate_independence():
    base = dh.Filters(year_range=(2013, 2024))
    inj = dh.Filters(year_range=(2013, 2024), severity="injury")
    m_inj = dh.build_mask(D, inj)
    m_all_sev = dh.build_mask(D, inj, exclude=("severity",))
    k = dh.kpis(D, m_inj, m_all_sev)
    k0 = dh.kpis(D, dh.build_mask(D, base), dh.build_mask(D, base))
    assert k["crashes"] == k["injury_crashes"]
    assert approx(k["injury_pct"], k0["injury_pct"], 1e-12)  # rate NOT forced to 100%
    assert k["injury_pct"] < 99


def test_exclude_parameter():
    f = dh.Filters(boroughs=("BROOKLYN",), year_range=(2015, 2016))
    only_b = dh.build_mask(D, f, exclude=("year",))
    only_y = dh.build_mask(D, f, exclude=("borough",))
    both = dh.build_mask(D, f)
    assert both.sum() == (only_b & only_y).sum()
    assert only_b.sum() > both.sum() and only_y.sum() > both.sum()


def test_grid_aggregate_and_cell_filter_consistent():
    f = dh.Filters(year_range=(2012, 2025))
    m = dh.build_mask(D, f)
    g = dh.grid_aggregate(D, m, 250)
    assert g["crashes"].sum() == (m & np.isfinite(D.lat)).sum()
    top = g.sort_values("crashes", ascending=False).iloc[0]
    fc = dh.Filters(year_range=(2012, 2025), cell=(250, int(top["ix"]), int(top["iy"])))
    mc = dh.build_mask(D, fc)
    assert mc.sum() == top["crashes"]
    # centre of cell falls inside the cell
    ix, iy = dh.cell_index(np.array([top["lat"]]), np.array([top["lon"]]), 250)
    assert int(ix[0]) == int(top["ix"]) and int(iy[0]) == int(top["iy"])
    # injury rate per cell uses known-injury denominator
    assert approx(top["injury_rate"], 100 * top["injury_crashes"] / top["inj_known"], 1e-9)


def test_over_representation_identity():
    m = dh.build_mask(D, dh.Filters(year_range=(2012, 2025)))
    r = dh.grid_over_representation(D, m, m, 500, min_total=30)
    assert len(r) > 0
    assert np.allclose(r["ratio"], 1.0)


def test_over_representation_detects_concentration():
    f_all = dh.Filters(year_range=(2012, 2025))
    f_sub = dh.Filters(year_range=(2012, 2025), factors=("Unsafe Speed",))
    r = dh.grid_over_representation(
        D, dh.build_mask(D, f_sub), dh.build_mask(D, f_all, exclude=("factor",)), 500, 30)
    assert (r["ratio"] >= 0).all() and r["ratio"].notna().all()


def test_wilson_interval():
    lo, hi = dh.wilson_interval([50], [100])
    assert 40.3 < lo[0] < 40.5 and 59.5 < hi[0] < 59.7
    lo, hi = dh.wilson_interval([0], [0])
    assert np.isnan(lo[0]) and np.isnan(hi[0])


def test_filters_json_round_trip():
    f = dh.Filters(boroughs=("QUEENS",), factors=("Unsafe Speed",), days=(1, 2),
                   cell=(250, 10, 20), severity="fatal", hour_range=(5, 9))
    assert dh.Filters.from_json(f.to_json()) == f


def test_borough_filled_equals_reported_without_boundaries():
    assert not META["has_filled_borough"]
    assert (PROC["borough_code"] == PROC["borough_filled_code"]).all()


def test_zero_row_selection_does_not_crash():
    f = dh.Filters(year_range=(2012, 2012), boroughs=("STATEN ISLAND",), factors=("Unsafe Speed",),
                   severity="fatal", hour_range=(3, 3))
    m = dh.build_mask(D, f)
    k = dh.kpis(D, m, m)
    assert k["crashes"] == m.sum()
    dh.by_borough(D, m); dh.by_year(D, m); dh.by_month(D, m); dh.by_hour(D, m)
    dh.dow_hour(D, m); dh.factor_table(D, m); dh.factor_table(D, m, "any")
    dh.vehicle_table(D, m); dh.grid_aggregate(D, m, 250)


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:                    # noqa: BLE001
            failed += 1
            import traceback
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
