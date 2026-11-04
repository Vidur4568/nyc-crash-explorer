"""Tests for utils/insights.py and the cache-key helpers (SYNTHETIC data).

Each statement is checked against an independent pandas computation so the
text can never drift from the numbers.
"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.make_synthetic_data import make_raw            # noqa: E402
from utils import data_helpers as dh, insights as ins     # noqa: E402
from utils.prepare import transform_raw                    # noqa: E402
from utils.schema import DAY_NAMES, FACTOR_COLS           # noqa: E402

RAW = make_raw()
PROC, META = transform_raw(RAW)
D = dh.CrashData(PROC, META)
F = dh.Filters(year_range=(2013, 2024))
M = dh.build_mask(D, F)
ORA = RAW.drop_duplicates("COLLISION_ID").copy()
ORA["YEAR"] = pd.to_datetime(ORA["CRASH DATE"], format="%m/%d/%Y").dt.year
ORA["BOROUGH"] = ORA["BOROUGH"].str.strip().str.upper()
ORA = ORA[ORA["YEAR"].between(2013, 2024)]


def test_borough_counts_matches_pandas():
    bt = dh.by_borough(D, M)
    s = ins.borough_counts(bt)
    vc = ORA["BOROUGH"].value_counts()
    top, n = vc.index[0], int(vc.iloc[0])
    assert top.title() in s and f"{n:,}" in s
    share = round(100 * n / vc.sum())
    assert f"{share}%" in s


def test_borough_rates_range_matches_pandas():
    bt = dh.by_borough(D, M)
    s = ins.borough_rates(bt)
    r = {}
    for b, sub in ORA.groupby("BOROUGH"):
        kn = sub["NUMBER OF PERSONS INJURED"].notna()
        r[b] = 100 * (sub["NUMBER OF PERSONS INJURED"][kn] > 0).mean()
    hi, lo = max(r, key=r.get), min(r, key=r.get)
    assert f"{r[hi]:.1f}%" in s and f"{r[lo]:.1f}%" in s
    assert hi.title() in s and lo.title() in s


def test_time_trend_uses_complete_years_only():
    yt = dh.by_year(D, dh.build_mask(D, F, exclude=("year",)))
    s = ins.time_trend(yt)
    comp = yt[~yt["partial"]]
    peak = comp.loc[comp["crashes"].idxmax()]
    assert str(int(peak["year"])) in s
    # partial years must never be reported as the peak
    assert int(peak["year"]) not in META["partial_years"]


def test_hour_profile_matches_pandas():
    ht = dh.by_hour(D, M)
    s = ins.hour_profile(ht, 200)
    assert f"{int(ht.loc[ht['crashes'].idxmax(), 'hour']):02d}:00" in s
    e = ht[ht["inj_known"] >= 200]
    assert f"{e['injury_rate'].max():.1f}%" in s


def test_factor_statements():
    mask = dh.build_mask(D, F, exclude=("factor", "severity"))
    ft = dh.factor_table(D, mask, "vehicle1")
    cov = dh.factor_coverage(D, mask)
    s = ins.factor_frequency(ft, cov["with_factor"])
    top = ft.loc[ft["crashes"].idxmax()]
    assert top["factor"] in s and f"{int(top['crashes']):,}" in s
    kk = dh.kpis(D, mask, mask)
    s2 = ins.factor_severity(ft, kk["injury_pct"], 100)
    e = ft[ft["inj_known"] >= 100]
    assert e.loc[e["injury_rate"].idxmax(), "factor"] in s2
    assert ins.factor_severity(ft, kk["injury_pct"], 10**9) is None       # nothing qualifies -> no claim
    assert ins.scatter_quadrant(ft, kk["injury_pct"], 100) is not None


def test_road_users_percentages():
    yt = dh.by_year(D, dh.build_mask(D, F, exclude=("year",)))
    s = ins.road_users(yt)
    c = yt[~yt["partial"]]
    f, l = c.iloc[0], c.iloc[-1]
    exp = 100 * (l["ped_inj"] - f["ped_inj"]) / f["ped_inj"]
    assert f"{exp:+.0f}%" in s


def test_map_concentration():
    g = dh.grid_aggregate(D, M, 250)
    s = ins.map_concentration(g, 10)
    share = round(100 * g.nlargest(10, "crashes")["crashes"].sum() / g["crashes"].sum())
    assert f"{share}%" in s
    assert ins.map_concentration(g.iloc[0:0]) is None


def test_vs_city():
    kb = dh.kpis(D, M, M)
    f = replace(F, boroughs=("BROOKLYN",))
    m = dh.build_mask(D, f)
    k = dh.kpis(D, m, m)
    v = ins.vs_city(k, kb)
    assert abs(v["share_pct"] - 100 * k["crashes"] / kb["crashes"]) < 1e-9
    assert abs(v["injury_pp"] - (k["injury_pct"] - kb["injury_pct"])) < 1e-9


def test_empty_inputs_return_none():
    empty = dh.by_borough(D, np.zeros(D.n, bool))
    assert ins.borough_counts(empty) is None
    assert ins.borough_rates(empty) is None
    assert ins.hour_profile(dh.by_hour(D, np.zeros(D.n, bool))) is None
    assert ins.heatmap_peak(dh.dow_hour(D, np.zeros(D.n, bool))) is None


def test_limits_are_data_driven():
    mask = dh.build_mask(D, F)
    k = dh.kpis(D, mask, mask)
    bt = dh.by_borough(D, mask)
    out = ins.limits(META, k, bt, 65.0)
    unk = bt.loc[bt["borough"] == "Unknown", "crashes"].iloc[0]
    assert f"{round(100 * unk / bt['crashes'].sum())}%" in out[0]
    assert any("Partial years" in x for x in out)


# ---------------------------------------------------------------- cache keys
def test_canonical_key_masks_identical():
    f = dh.Filters(boroughs=("QUEENS",), year_range=(2014, 2019), factors=("Unsafe Speed",),
                   vehicles=("Van",), severity="injury", days=(1,), hour_range=(6, 9), cell=(250, 3, 4))
    for ex in [(), ("borough", "severity", "cell"), ("factor", "severity"), ("hour", "dow", "severity"),
               ("year",), ("vehicle", "severity"), ("cell",)]:
        a = dh.build_mask(D, f, ex)
        b = dh.build_mask(D, dh.Filters.from_json(dh.canonical_key(f, ex)), ex)
        assert (a == b).all(), ex


def test_canonical_key_ignores_excluded_dimension():
    a = dh.Filters(boroughs=("QUEENS",), cell=(250, 1, 2))
    b = dh.Filters(boroughs=("BRONX",), cell=None)
    ex = ("borough", "cell")
    assert dh.canonical_key(a, ex) == dh.canonical_key(b, ex)
    assert dh.canonical_key(a, ()) != dh.canonical_key(b, ())


def test_baseline_filters():
    f = dh.Filters(boroughs=("QUEENS",), year_range=(2015, 2016), factors=("Unsafe Speed",), severity="fatal")
    b = dh.baseline_filters(f)
    assert b.year_range == (2015, 2016) and not b.boroughs and not b.factors and b.severity == "all"
    assert dh.is_filtered(f) and not dh.is_filtered(b)


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}")
        except Exception as e:                    # noqa: BLE001
            failed += 1
            import traceback; print(f"FAIL  {name}: {type(e).__name__}: {e}"); traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
