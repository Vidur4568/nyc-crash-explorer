"""Plain-English statements computed from the aggregated tables.

Rules (so the dashboard never "invents" findings):
* Every number in a sentence is read from the table passed in.
* Wording is descriptive: "recorded", "associated", never "caused".
* Comparisons of rates mention whether 95% intervals overlap.
* Each function returns None when the data cannot support a statement.

Text uses **bold** markers; the UI converts them to HTML.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from utils.schema import DAY_NAMES, borough_label


def _n(x) -> str:
    return f"{int(round(float(x))):,}"


def _p(x, d: int = 1) -> str:
    return f"{float(x):.{d}f}%"


def _hh(h) -> str:
    return f"{int(h):02d}:00"


# ---------------------------------------------------------------- comparisons with the city
def vs_city(k: dict, kb: dict) -> dict:
    """Selection vs citywide baseline (same years)."""
    share = 100.0 * k["crashes"] / kb["crashes"] if kb["crashes"] else float("nan")
    return {
        "share_pct": share,
        "injury_pp": k["injury_pct"] - kb["injury_pct"],
        "fatality_pp": k["fatality_pct"] - kb["fatality_pct"],
    }


# ---------------------------------------------------------------- where
def borough_counts(bt: pd.DataFrame) -> Optional[str]:
    bk = bt[(bt["borough"] != "Unknown") & (bt["crashes"] > 0)]
    if bk.empty:
        return None
    top = bk.loc[bk["crashes"].idxmax()]
    if len(bk) == 1:
        return f"**{borough_label(top['borough'])}** has {_n(top['crashes'])} recorded crashes in this selection."
    share = 100 * top["crashes"] / bk["crashes"].sum()
    return (f"**{borough_label(top['borough'])}** recorded the most crashes ({_n(top['crashes'])}, "
            f"{share:.0f}% of crashes with a known borough).")


def borough_rates(bt: pd.DataFrame) -> Optional[str]:
    r = bt[(bt["borough"] != "Unknown") & (bt["inj_known"] > 0)].sort_values("injury_rate", ascending=False)
    if len(r) < 2:
        return None
    a, b = r.iloc[0], r.iloc[-1]
    s = (f"The injury rate runs from **{_p(b['injury_rate'])}** in {borough_label(b['borough'])} to "
         f"**{_p(a['injury_rate'])}** in {borough_label(a['borough'])}. ")
    s += ("The 95% intervals of these two do not overlap." if a["ci_low"] > b["ci_high"]
          else "Their 95% intervals overlap, so the gap may not be meaningful.")
    return s


def map_concentration(grid: pd.DataFrame, top_n: int = 10) -> Optional[str]:
    if grid.empty or grid["crashes"].sum() == 0:
        return None
    tot = grid["crashes"].sum()
    k = min(top_n, len(grid))
    top = grid.nlargest(k, "crashes")["crashes"].sum()
    return (f"The {k} busiest cells hold **{100 * top / tot:.0f}%** of the {_n(tot)} mapped crashes "
            f"(spread over {len(grid):,} cells). Busy cells mostly reflect heavy traffic, not necessarily higher risk.")


# ---------------------------------------------------------------- when
def time_trend(yt: pd.DataFrame, metric: str = "crashes", label: str = "crashes") -> Optional[str]:
    c = yt[(~yt["partial"]) & (yt["crashes"] > 0)]
    if len(c) < 2:
        return None
    peak = c.loc[c[metric].idxmax()]
    last = c.iloc[-1]
    if peak[metric] <= 0:
        return None
    if int(peak["year"]) == int(last["year"]):
        return f"Among complete years, {label} are highest in **{int(peak['year'])}** ({_n(peak[metric])})."
    pct = 100 * (last[metric] - peak[metric]) / peak[metric]
    return (f"Among complete years, {label} peaked in **{int(peak['year'])}** ({_n(peak[metric])}); "
            f"in {int(last['year'])} there were **{abs(pct):.0f}% {'fewer' if pct < 0 else 'more'}**. "
            "The data alone cannot say why.")


def hour_profile(ht: pd.DataFrame, min_n: int = 200) -> Optional[str]:
    if ht["crashes"].sum() == 0:
        return None
    pk = ht.loc[ht["crashes"].idxmax()]
    s = f"Crash volume peaks at **{_hh(pk['hour'])}** ({_n(pk['crashes'])} crashes). "
    e = ht[ht["inj_known"] >= min_n]
    if len(e) >= 2:
        hi, lo = e.loc[e["injury_rate"].idxmax()], e.loc[e["injury_rate"].idxmin()]
        s += (f"The injury rate is highest at **{_hh(hi['hour'])}** ({_p(hi['injury_rate'])}) and lowest at "
              f"**{_hh(lo['hour'])}** ({_p(lo['injury_rate'])})")
        s += (" — so the busiest hour is not the most severe one." if int(hi["hour"]) != int(pk["hour"]) else ".")
    return s


def heatmap_peak(dhm: pd.DataFrame, min_n: int = 50) -> Optional[str]:
    if dhm["crashes"].sum() == 0:
        return None
    pk = dhm.loc[dhm["crashes"].idxmax()]
    by_day = dhm.groupby("dow")["crashes"].sum()
    s = (f"The busiest slot is **{DAY_NAMES[int(pk['dow'])]} {_hh(pk['hour'])}** ({_n(pk['crashes'])} crashes); "
         f"**{DAY_NAMES[int(by_day.idxmax())]}** has the most crashes overall.")
    e = dhm[dhm["inj_known"] >= min_n]
    if len(e):
        hi = e.loc[e["injury_rate"].idxmax()]
        s += (f" Among slots with ≥{min_n} crashes the injury rate is highest on "
              f"**{DAY_NAMES[int(hi['dow'])]} {_hh(hi['hour'])}** ({_p(hi['injury_rate'])}).")
    return s


# ---------------------------------------------------------------- factors
def factor_frequency(ft: pd.DataFrame, with_factor: int) -> Optional[str]:
    t = ft[ft["crashes"] > 0]
    if t.empty or not with_factor:
        return None
    top = t.loc[t["crashes"].idxmax()]
    return (f"**{top['factor']}** is the most frequently recorded factor ({_n(top['crashes'])} crashes, "
            f"{100 * top['crashes'] / with_factor:.0f}% of crashes that have a specified factor).")


def factor_severity(ft: pd.DataFrame, overall: float, min_c: int) -> Optional[str]:
    e = ft[ft["inj_known"] >= min_c]
    if e.empty or not np.isfinite(overall):
        return None
    top = e.loc[e["injury_rate"].idxmax()]
    above = int((e["ci_low"] > overall).sum())
    return (f"Among factors with ≥{min_c:,} crashes, **{top['factor']}** has the highest injury rate: "
            f"{_p(top['injury_rate'])} (95% CI {top['ci_low']:.1f}–{top['ci_high']:.1f}%) versus "
            f"{_p(overall)} for all crashes here. {above} of {len(e)} factors sit above that overall rate "
            "beyond sampling noise.")


def scatter_quadrant(ft: pd.DataFrame, overall: float, min_c: int) -> Optional[str]:
    e = ft[ft["inj_known"] >= min_c]
    if len(e) < 3 or not np.isfinite(overall):
        return None
    common = e["crashes"] >= e["crashes"].median()
    both = e[common & (e["injury_rate"] > overall)].sort_values("crashes", ascending=False)
    if both.empty:
        return "No frequently recorded factor has an injury rate above the overall rate in this selection."
    names = ", ".join(f"**{x}**" for x in both["factor"].head(3))
    return f"Recorded often *and* with an above-average injury rate: {names}."


# ---------------------------------------------------------------- who
def road_users(yt: pd.DataFrame) -> Optional[str]:
    c = yt[(~yt["partial"]) & (yt["crashes"] > 0)]
    if len(c) < 2:
        return None
    f, l = c.iloc[0], c.iloc[-1]
    parts = []
    for col, name in (("ped_inj", "pedestrians"), ("cyc_inj", "cyclists"), ("mot_inj", "motorists")):
        if f[col] > 0:
            parts.append(f"{name} **{100 * (l[col] - f[col]) / f[col]:+.0f}%**")
    if not parts:
        return None
    return (f"People injured, {int(f['year'])} → {int(l['year'])}: " + ", ".join(parts)
            + ". These are counts of people, not rates; no travel-volume data is included.")


def vehicle_rates(vt: pd.DataFrame, overall: float, min_c: int) -> Optional[str]:
    e = vt[vt["inj_known"] >= min_c]
    if len(e) < 2:
        return None
    hi, lo = e.loc[e["injury_rate"].idxmax()], e.loc[e["injury_rate"].idxmin()]
    return (f"Crashes involving **{hi['vehicle_group']}** have the highest injury rate ({_p(hi['injury_rate'])}); "
            f"those involving **{lo['vehicle_group']}** the lowest ({_p(lo['injury_rate'])}). "
            "'Involving' does not mean at fault.")


# ---------------------------------------------------------------- closing slide
def takeaways(tables: dict) -> list[str]:
    """Collect the headline statements for the current selection."""
    out = [
        borough_counts(tables["bt"]), borough_rates(tables["bt"]),
        hour_profile(tables["ht"]), heatmap_peak(tables["dh"]),
        factor_frequency(tables["ft"], tables["with_factor"]),
        factor_severity(tables["ft"], tables["overall"], tables["min_c"]),
        road_users(tables["yt"]),
    ]
    return [x for x in out if x]


def limits(meta: dict, k: dict, bt: pd.DataFrame, factor_pct_with: float) -> list[str]:
    """Data-aware limitations for the current selection."""
    tot = bt["crashes"].sum()
    unk = bt.loc[bt["borough"] == "Unknown", "crashes"].sum()
    out = []
    if tot:
        out.append(f"**{100 * unk / tot:.0f}%** of crashes here have no recorded borough and are left out of borough comparisons.")
    if np.isfinite(factor_pct_with):
        out.append(f"**{100 - factor_pct_with:.0f}%** of crashes have no specified contributing factor; "
                   "factors are police-recorded, not proof of cause.")
    out.append(f"**{100 - k['pct_with_valid_coords']:.0f}%** of crashes lack valid coordinates and cannot appear on the map.")
    if meta.get("partial_years"):
        out.append("Partial years (" + ", ".join(map(str, meta["partial_years"])) + ") are excluded from the default range.")
    out.append("There is no traffic-volume or population data, so counts and rates describe recorded crashes, not individual risk.")
    return out
