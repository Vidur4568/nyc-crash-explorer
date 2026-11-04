"""Streamlit cache layer.

Pure functions live in utils.data_helpers. Each is wrapped with
@st.cache_data and keyed on a *canonical* filter string: filters a given
table ignores (see `ex`) are reset before the key is built, so e.g. the map
grid is NOT recomputed when you click a hotspot, and the borough charts are
NOT recomputed when you change borough. The 2M-row `CrashData` object is
passed as `_d` (leading underscore = not hashed) and loaded once with
@st.cache_resource, shared by all sessions.

Call style:   cached.hour_table(d, fkey)           # default `ex`
              cached.factor_table(d, fkey, ex=("factor", "severity"))
"""
from __future__ import annotations

import functools
from dataclasses import replace
from pathlib import Path

import streamlit as st

from utils import data_helpers as dh

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"


def data_available() -> bool:
    return (PROCESSED_DIR / "crashes.parquet").exists() and (PROCESSED_DIR / "meta.json").exists()


@st.cache_resource(show_spinner="Loading crash data…")
def load_data() -> dh.CrashData:
    return dh.CrashData.load(PROCESSED_DIR)


def _mask(_d, fkey: str, ex: tuple):
    return dh.build_mask(_d, dh.Filters.from_json(fkey), ex)


def canon(default_ex: tuple):
    """Decorator: public fn(_d, fkey, *args, ex=default_ex) -> cached inner(_d, canon_key, ex, *args)."""
    def deco(fn):
        inner = st.cache_data(show_spinner=False, max_entries=96)(fn)

        @functools.wraps(fn)
        def wrapper(_d, fkey: str, *args, ex: tuple = default_ex):
            ex = tuple(ex)
            ck = dh.canonical_key(dh.Filters.from_json(fkey), ex)
            return inner(_d, ck, ex, *args)
        return wrapper
    return deco


# ----------------------------------------------------------------------------- headline numbers
@canon(())
def kpis(_d, fkey, ex):
    return dh.kpis(_d, _mask(_d, fkey, ()), _mask(_d, fkey, ("severity",)))


def baseline_kpis(_d, fkey: str) -> dict:
    """Citywide comparison (same years, nothing else filtered)."""
    f = dh.Filters.from_json(fkey)
    return kpis(_d, dh.baseline_filters(f).to_json())


# ----------------------------------------------------------------------------- tables
@canon(("borough", "severity", "cell"))
def borough_table(_d, fkey, ex):
    f = dh.Filters.from_json(fkey)
    return dh.by_borough(_d, _mask(_d, fkey, ex), f.use_filled_borough)


@canon(("year",))
def year_table(_d, fkey, ex):
    return dh.by_year(_d, _mask(_d, fkey, ex))


@canon(("year",))
def month_table(_d, fkey, ex):
    return dh.by_month(_d, _mask(_d, fkey, ex))


@canon(("hour", "severity"))
def hour_table(_d, fkey, ex):
    return dh.by_hour(_d, _mask(_d, fkey, ex))


@canon(("hour", "dow", "severity"))
def dow_hour_table(_d, fkey, ex):
    return dh.dow_hour(_d, _mask(_d, fkey, ex))


@canon(("factor", "severity"))
def factor_table(_d, fkey, ex):
    f = dh.Filters.from_json(fkey)
    return dh.factor_table(_d, _mask(_d, fkey, ex), f.factor_scope)


@canon(("factor", "severity"))
def factor_coverage(_d, fkey, ex):
    f = dh.Filters.from_json(fkey)
    return dh.factor_coverage(_d, _mask(_d, fkey, ex), f.factor_scope)


@canon(("vehicle", "severity"))
def vehicle_table(_d, fkey, ex):
    return dh.vehicle_table(_d, _mask(_d, fkey, ex))


@canon(("factor", "severity"))
def overall_injury_rate(_d, fkey, ex) -> float:
    m = _mask(_d, fkey, ex)
    return dh.kpis(_d, m, m)["injury_pct"]


# ----------------------------------------------------------------------------- map
@canon(("cell",))
def grid(_d, fkey, ex, size_m: int):
    return dh.grid_aggregate(_d, _mask(_d, fkey, ex), size_m)


@canon(("cell", "severity", "factor"))
def over_representation(_d, fkey, ex, factor: str, size_m: int, min_total: int):
    """Where is `factor` over/under-represented relative to all crashes (other filters apply)."""
    f = dh.Filters.from_json(fkey)
    f_sub = replace(f, factors=(factor,))
    m_sub = dh.build_mask(_d, f_sub, ("cell", "severity"))
    m_all = dh.build_mask(_d, f_sub, ("cell", "severity", "factor"))
    return dh.grid_over_representation(_d, m_sub, m_all, size_m, min_total)


@canon(("severity", "cell", "borough"))
def area_tables(_d, fkey, ex, borough: str):
    """Tables for the borough-vs-borough view (one borough forced)."""
    f = dh.Filters.from_json(fkey)
    m = dh.build_mask(_d, replace(f, boroughs=(borough,)), ("severity", "cell"))
    return {"kpi": dh.kpis(_d, m, m), "hour": dh.by_hour(_d, m),
            "factor": dh.factor_table(_d, m, f.factor_scope)}
