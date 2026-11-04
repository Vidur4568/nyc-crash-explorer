"""Loading, filtering and aggregation logic for NYC Crash Explorer.

No Streamlit / Plotly imports here: everything takes a `CrashData` object and
a `Filters` object and returns plain numbers, arrays or DataFrames. That keeps
the maths testable and keeps "processing" separate from "presentation".

Terminology used everywhere
---------------------------
crash            one row of the dataset (one COLLISION_ID)
injury crash     crash with >= 1 person injured       (counts crashes)
persons injured  sum of NUMBER OF PERSONS INJURED     (counts people)
injury rate      injury crashes / crashes whose injury count is recorded
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from utils.schema import (
    GRID_LAT0, GRID_LON0, GRID_REF_LAT, METRES_PER_DEG_LAT, UNKNOWN_BOROUGH_CODE,
)

Z95 = 1.959964


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Filters:
    """All sidebar selections. Empty tuple = 'no restriction'."""
    boroughs: tuple = ()                   # e.g. ("BROOKLYN",)
    year_range: tuple = (2013, 2024)
    factors: tuple = ()                    # canonical factor names
    factor_scope: str = "vehicle1"         # "vehicle1" | "any"
    vehicles: tuple = ()                   # vehicle-group names
    severity: str = "all"                  # "all" | "injury" | "fatal"
    days: tuple = ()                       # 0=Mon .. 6=Sun
    hour_range: tuple = (0, 23)
    use_filled_borough: bool = False
    cell: Optional[tuple] = None           # (size_m, ix, iy) selected map hotspot

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, s: str) -> "Filters":
        d = json.loads(s)
        for k in ("boroughs", "year_range", "factors", "vehicles", "days", "hour_range"):
            d[k] = tuple(d[k])
        d["cell"] = tuple(d["cell"]) if d.get("cell") else None
        return cls(**d)


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------
class CrashData:
    """Holds the processed crash table as NumPy arrays for fast masking."""

    def __init__(self, df: pd.DataFrame, meta: dict):
        self.meta = meta
        self.n = len(df)
        for col in df.columns:
            setattr(self, col, df[col].to_numpy())
        self.factor1_shift = self.factor1.astype(np.int16) + 1     # 0 = no usable factor
        self.factors: list[str] = list(meta["factors"])
        self.factor_index = {f: i for i, f in enumerate(self.factors)}
        self.vehicle_groups: list[str] = list(meta["vehicle_groups"])
        self.vehicle_index = {v: i for i, v in enumerate(self.vehicle_groups)}
        self.borough_names: list[str] = list(meta["boroughs"])
        self.partial_years = set(meta["partial_years"])
        self.years = list(meta["years"])

    @classmethod
    def load(cls, folder: str | Path) -> "CrashData":
        folder = Path(folder)
        df = pd.read_parquet(folder / "crashes.parquet")
        meta = json.loads((folder / "meta.json").read_text())
        return cls(df, meta)

    def borough_array(self, use_filled: bool) -> np.ndarray:
        return self.borough_filled_code if use_filled else self.borough_code

    @property
    def complete_years(self) -> list[int]:
        return [y for y in self.years if y not in self.partial_years]


# ---------------------------------------------------------------------------
# Grid helpers (shared by map aggregation and the clicked-cell filter)
# ---------------------------------------------------------------------------
def grid_steps(size_m: float) -> tuple[float, float]:
    """Cell height/width in degrees for a square cell of `size_m` metres."""
    dlat = size_m / METRES_PER_DEG_LAT
    dlon = size_m / (METRES_PER_DEG_LAT * np.cos(np.radians(GRID_REF_LAT)))
    return dlat, dlon


def cell_index(lat: np.ndarray, lon: np.ndarray, size_m: float):
    dlat, dlon = grid_steps(size_m)
    iy = np.floor((lat.astype(np.float64) - GRID_LAT0) / dlat)
    ix = np.floor((lon.astype(np.float64) - GRID_LON0) / dlon)
    return ix, iy


def cell_center(ix, iy, size_m: float):
    dlat, dlon = grid_steps(size_m)
    return GRID_LAT0 + (np.asarray(iy) + 0.5) * dlat, GRID_LON0 + (np.asarray(ix) + 0.5) * dlon


# ---------------------------------------------------------------------------
# Masks
# ---------------------------------------------------------------------------
def _lut(size: int, selected: Sequence[int]) -> np.ndarray:
    lut = np.zeros(size, dtype=bool)
    lut[list(selected)] = True
    return lut


def build_mask(d: CrashData, f: Filters, exclude: Sequence[str] = ()) -> np.ndarray:
    """Boolean mask of crashes that satisfy `f`.

    `exclude` skips named filters, e.g. a borough chart ignores the borough
    filter so every borough stays visible (the selection is highlighted).
    Names: year, borough, factor, vehicle, severity, dow, hour, cell.
    """
    ex = set(exclude)
    m = np.ones(d.n, dtype=bool)

    if "year" not in ex:
        y0, y1 = f.year_range
        m &= (d.year >= y0) & (d.year <= y1)

    if "borough" not in ex and f.boroughs:
        codes = [d.borough_names.index(b) for b in f.boroughs]
        m &= _lut(len(d.borough_names), codes)[d.borough_array(f.use_filled_borough)]

    if "factor" not in ex and f.factors:
        idx = [d.factor_index[x] for x in f.factors]
        if f.factor_scope == "any":
            bits = np.uint64(0)
            for i in idx:
                bits |= np.uint64(1) << np.uint64(i)
            m &= (d.factor_mask & bits) != 0           # counts each crash once
        else:
            m &= _lut(len(d.factors) + 1, [i + 1 for i in idx])[d.factor1_shift]

    if "vehicle" not in ex and f.vehicles:
        bits = np.uint16(0)
        for v in f.vehicles:
            bits |= np.uint16(1) << np.uint16(d.vehicle_index[v])
        m &= (d.veh_mask & bits) != 0

    if "severity" not in ex:
        if f.severity == "injury":
            m &= d.any_injury
        elif f.severity == "fatal":
            m &= d.any_fatality

    if "dow" not in ex and f.days:
        m &= _lut(7, f.days)[d.dow]

    if "hour" not in ex and tuple(f.hour_range) != (0, 23):
        h0, h1 = f.hour_range
        m &= (d.hour >= h0) & (d.hour <= h1)          # unknown hour (-1) is excluded

    if "cell" not in ex and f.cell:
        size, ix, iy = f.cell
        cx, cy = cell_index(d.lat, d.lon, size)       # NaN (no coords) never equals
        m &= (cx == ix) & (cy == iy)

    return m


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------
def wilson_interval(k, n, z: float = Z95):
    """95% Wilson score interval for a proportion (returned in %)."""
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = k / n
        denom = 1 + z**2 / n
        centre = (p + z**2 / (2 * n)) / denom
        half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    lo, hi = (centre - half) * 100, (centre + half) * 100
    return np.where(n > 0, lo, np.nan), np.where(n > 0, hi, np.nan)


def _rate(k, n):
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(n > 0, 100.0 * k / n, np.nan)


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    """Add rate columns + CI to a table with the standard count columns."""
    df["injury_rate"] = _rate(df["injury_crashes"], df["inj_known"])
    df["fatality_rate"] = _rate(df["fatal_crashes"], df["kill_known"])
    lo, hi = wilson_interval(df["injury_crashes"], df["inj_known"])
    df["ci_low"], df["ci_high"] = lo, hi
    return df


def _group_counts(d: CrashData, mask: np.ndarray, codes: np.ndarray, k: int) -> pd.DataFrame:
    """Aggregate the standard measures by integer `codes` (0..k-1)."""
    c = codes[mask]

    def w(arr):
        return np.bincount(c, weights=arr[mask], minlength=k)

    df = pd.DataFrame({
        "crashes": np.bincount(c, minlength=k),
        "injury_crashes": w(d.any_injury),
        "inj_known": w(d.inj_known),
        "fatal_crashes": w(d.any_fatality),
        "kill_known": w(d.kill_known),
        "persons_injured": w(d.injured),
        "persons_killed": w(d.killed),
        "ped_inj": w(d.ped_inj), "cyc_inj": w(d.cyc_inj), "mot_inj": w(d.mot_inj),
        "ped_kill": w(d.ped_kill), "cyc_kill": w(d.cyc_kill), "mot_kill": w(d.mot_kill),
    })
    return _finish(df)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
def kpis(d: CrashData, mask: np.ndarray, mask_all_severity: np.ndarray) -> dict:
    """Headline numbers.

    Counts use `mask` (all filters). The two percentages use
    `mask_all_severity` (same filters except the severity filter), because an
    'injury rate' computed on injury-only crashes is trivially 100%.
    """
    n = int(mask.sum())
    r = mask_all_severity
    n_r = int(r.sum())
    inj_known = int((r & d.inj_known).sum())
    kil_known = int((r & d.kill_known).sum())
    inj_crashes = int((r & d.any_injury).sum())
    fatal_crashes = int((r & d.any_fatality).sum())
    return {
        "crashes": n,
        "persons_injured": int(d.injured[mask].sum()),
        "persons_killed": int(d.killed[mask].sum()),
        "injury_crashes": inj_crashes,
        "fatal_crashes": fatal_crashes,
        "crashes_for_rates": n_r,
        "injury_pct": 100.0 * inj_crashes / inj_known if inj_known else float("nan"),
        "fatality_pct": 100.0 * fatal_crashes / kil_known if kil_known else float("nan"),
        "injury_missing": int((mask & ~d.inj_known).sum()),
        "pct_with_valid_coords": 100.0 * float(np.isfinite(d.lat[mask]).mean()) if n else float("nan"),
    }


# ---------------------------------------------------------------------------
# Group tables
# ---------------------------------------------------------------------------
def by_borough(d: CrashData, mask: np.ndarray, use_filled: bool = False) -> pd.DataFrame:
    """One row per borough, INCLUDING 'Unknown' so totals reconcile."""
    k = len(d.borough_names)
    df = _group_counts(d, mask, d.borough_array(use_filled).astype(np.int64), k)
    df.insert(0, "borough", d.borough_names)
    return df


def by_year(d: CrashData, mask: np.ndarray) -> pd.DataFrame:
    y0 = min(d.years)
    k = max(d.years) - y0 + 1
    df = _group_counts(d, mask, (d.year.astype(np.int64) - y0), k)
    df.insert(0, "year", np.arange(y0, y0 + k))
    df["partial"] = df["year"].isin(d.partial_years)
    return df[df["year"].isin(d.years)].reset_index(drop=True)


def by_month(d: CrashData, mask: np.ndarray) -> pd.DataFrame:
    m0 = int(d.ym.min())
    k = int(d.ym.max()) - m0 + 1
    df = _group_counts(d, mask, (d.ym.astype(np.int64) - m0), k)
    ym = np.arange(m0, m0 + k)
    df.insert(0, "month_start", pd.to_datetime(
        pd.DataFrame({"year": ym // 12, "month": ym % 12 + 1, "day": 1})))
    return df[df["crashes"] > 0].reset_index(drop=True) if mask.sum() else df.iloc[0:0]


def by_hour(d: CrashData, mask: np.ndarray) -> pd.DataFrame:
    known = mask & (d.hour >= 0)
    df = _group_counts(d, known, d.hour.astype(np.int64).clip(min=0), 24)
    df.insert(0, "hour", np.arange(24))
    return df


def dow_hour(d: CrashData, mask: np.ndarray) -> pd.DataFrame:
    """168 rows (7 days x 24 hours) with standard counts + rates."""
    known = mask & (d.hour >= 0)
    codes = d.dow.astype(np.int64) * 24 + d.hour.astype(np.int64).clip(min=0)
    df = _group_counts(d, known, codes, 168)
    df.insert(0, "dow", np.repeat(np.arange(7), 24))
    df.insert(1, "hour", np.tile(np.arange(24), 7))
    return df


def factor_table(d: CrashData, mask: np.ndarray, scope: str = "vehicle1") -> pd.DataFrame:
    """Crashes / injury rate for each contributing factor.

    scope="vehicle1": factor recorded for vehicle 1 only (matches the original
    notebook). scope="any": factor recorded for ANY of the five vehicles; a
    crash is counted once per factor even if several vehicles share it.
    'Unspecified' / missing / invalid are never included.
    """
    k = len(d.factors)
    if scope == "vehicle1":
        df = _group_counts(d, mask, d.factor1_shift.astype(np.int64), k + 1).iloc[1:].reset_index(drop=True)
    else:
        sel = mask & (d.factor_mask != 0)
        fm = d.factor_mask[sel]
        rows = []
        arrs = {c: getattr(d, c)[sel] for c in
                ("any_injury", "inj_known", "any_fatality", "kill_known", "injured", "killed",
                 "ped_inj", "cyc_inj", "mot_inj", "ped_kill", "cyc_kill", "mot_kill")}
        for i in range(k):
            hit = ((fm >> np.uint64(i)) & np.uint64(1)).astype(bool)
            rows.append({
                "crashes": int(hit.sum()),
                "injury_crashes": float(arrs["any_injury"][hit].sum()),
                "inj_known": float(arrs["inj_known"][hit].sum()),
                "fatal_crashes": float(arrs["any_fatality"][hit].sum()),
                "kill_known": float(arrs["kill_known"][hit].sum()),
                "persons_injured": float(arrs["injured"][hit].sum()),
                "persons_killed": float(arrs["killed"][hit].sum()),
                "ped_inj": float(arrs["ped_inj"][hit].sum()),
                "cyc_inj": float(arrs["cyc_inj"][hit].sum()),
                "mot_inj": float(arrs["mot_inj"][hit].sum()),
                "ped_kill": float(arrs["ped_kill"][hit].sum()),
                "cyc_kill": float(arrs["cyc_kill"][hit].sum()),
                "mot_kill": float(arrs["mot_kill"][hit].sum()),
            })
        df = _finish(pd.DataFrame(rows))
    df.insert(0, "factor", d.factors)
    return df


def factor_coverage(d: CrashData, mask: np.ndarray, scope: str = "vehicle1") -> dict:
    """How many crashes in the selection have a usable (not 'Unspecified') factor."""
    n = int(mask.sum())
    usable = int((mask & ((d.factor1 >= 0) if scope == "vehicle1" else (d.factor_mask != 0))).sum())
    return {"crashes": n, "with_factor": usable,
            "pct_with_factor": 100.0 * usable / n if n else float("nan")}


def vehicle_table(d: CrashData, mask: np.ndarray) -> pd.DataFrame:
    """Crashes INVOLVING each vehicle group (any of 5 slots; counted once)."""
    sel = mask & (d.veh_mask != 0)
    vm = d.veh_mask[sel]
    inj, known = d.any_injury[sel], d.inj_known[sel]
    fat, kknown = d.any_fatality[sel], d.kill_known[sel]
    rows = []
    for i, name in enumerate(d.vehicle_groups):
        hit = ((vm >> np.uint16(i)) & np.uint16(1)).astype(bool)
        rows.append({
            "vehicle_group": name,
            "crashes": int(hit.sum()),
            "injury_crashes": float(inj[hit].sum()),
            "inj_known": float(known[hit].sum()),
            "fatal_crashes": float(fat[hit].sum()),
            "kill_known": float(kknown[hit].sum()),
        })
    return _finish(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Geographic grid
# ---------------------------------------------------------------------------
def grid_aggregate(d: CrashData, mask: np.ndarray, size_m: float) -> pd.DataFrame:
    """Aggregate crashes with valid coordinates into square cells.

    Returns one row per non-empty cell: ix, iy, lat, lon (cell centre),
    crashes, injury_crashes, inj_known, fatal_crashes, persons_killed,
    injury_rate, fatality_rate.
    """
    sel = mask & np.isfinite(d.lat)
    cols = ["ix", "iy", "lat", "lon", "crashes", "injury_crashes", "inj_known",
            "fatal_crashes", "persons_killed", "injury_rate", "fatality_rate"]
    if not sel.any():
        return pd.DataFrame(columns=cols)
    ix, iy = cell_index(d.lat[sel], d.lon[sel], size_m)
    key = iy.astype(np.int64) * 1_000_000 + ix.astype(np.int64)
    uniq, inv = np.unique(key, return_inverse=True)
    k = len(uniq)
    cnt = np.bincount(inv, minlength=k)

    def w(arr):
        return np.bincount(inv, weights=arr[sel], minlength=k)

    uy, ux = uniq // 1_000_000, uniq % 1_000_000
    lat, lon = cell_center(ux, uy, size_m)
    df = pd.DataFrame({
        "ix": ux, "iy": uy, "lat": lat, "lon": lon, "crashes": cnt,
        "injury_crashes": w(d.any_injury), "inj_known": w(d.inj_known),
        "fatal_crashes": w(d.any_fatality), "persons_killed": w(d.killed),
    })
    df["injury_rate"] = _rate(df["injury_crashes"], df["inj_known"])
    df["fatality_rate"] = _rate(df["fatal_crashes"], df["crashes"])
    return df


def grid_over_representation(d: CrashData, mask_subset: np.ndarray, mask_all: np.ndarray,
                             size_m: float, min_total: int = 30) -> pd.DataFrame:
    """Compare WHERE a subset of crashes happens against where ALL crashes happen.

    For each cell:   ratio = (cell's share of subset crashes) /
                             (cell's share of all crashes)
    ratio > 1: the subset is over-represented in that cell relative to crash
    activity in general; < 1: under-represented. Only cells with at least
    `min_total` crashes overall are returned (small cells are too noisy).
    Purely descriptive: it is not a statistical test and not a risk measure.
    """
    a = grid_aggregate(d, mask_all, size_m)
    s = grid_aggregate(d, mask_subset, size_m)
    if a.empty:
        return a.assign(subset_crashes=[], ratio=[])
    tot_a = a["crashes"].sum()                 # all geocoded crashes, before thresholding
    a = a[a["crashes"] >= min_total].copy()
    s = s[["ix", "iy", "crashes"]].rename(columns={"crashes": "subset_crashes"})
    out = a.merge(s, on=["ix", "iy"], how="left")
    out["subset_crashes"] = out["subset_crashes"].fillna(0)
    tot_s = max(s["subset_crashes"].sum(), 1)
    out["ratio"] = (out["subset_crashes"] / tot_s) / (out["crashes"] / tot_a)
    return out


def top_hotspots(grid: pd.DataFrame, n: int = 10, min_crashes: int = 1) -> pd.DataFrame:
    g = grid[grid["crashes"] >= min_crashes].sort_values("crashes", ascending=False).head(n)
    return g.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cache-key helpers
# ---------------------------------------------------------------------------
_EX_RESET = {
    "borough": {"boroughs": ()},
    "year": {"year_range": (0, 9999)},
    "factor": {"factors": ()},
    "vehicle": {"vehicles": ()},
    "severity": {"severity": "all"},
    "dow": {"days": ()},
    "hour": {"hour_range": (0, 23)},
    "cell": {"cell": None},
}


def canonical_key(f: Filters, exclude: Sequence[str] = ()) -> str:
    """JSON key for `f` with the excluded filters reset to their defaults.

    A chart that ignores the borough filter should not be recomputed when the
    borough changes; normalising the cache key achieves that. The mask built
    from the canonical key is identical to the mask built from `f` with the
    same `exclude` (tested in tests/test_pipeline.py).
    """
    changes: dict = {}
    for name in exclude:
        changes.update(_EX_RESET.get(name, {}))
    return replace(f, **changes).to_json()


def baseline_filters(f: Filters) -> Filters:
    """'Citywide' comparison point: same years, everything else cleared."""
    return Filters(year_range=f.year_range, use_filled_borough=f.use_filled_borough)


def is_filtered(f: Filters) -> bool:
    """True when anything other than the year range narrows the data."""
    return bool(f.boroughs or f.factors or f.vehicles or f.days or f.cell
                or f.severity != "all" or tuple(f.hour_range) != (0, 23))
