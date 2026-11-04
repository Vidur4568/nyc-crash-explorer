"""Sidebar filters + session-state plumbing + quick selectors.

All widget state lives in st.session_state under `f_*` keys so that (a) the
map can set a borough/cell when clicked, (b) the quick selectors (borough
buttons, factor pills) can drive the same state, and (c) 'Reset' works.
Widgets are created WITHOUT default arguments; defaults come from `init_state()`.
"""
from __future__ import annotations

import streamlit as st

from components.ui import sb_heading
from utils.data_helpers import CrashData, Filters, is_filtered
from utils.schema import BOROUGHS, DAY_NAMES, borough_label

YEAR_MODES = ["Complete years only", "All available (incl. partial years)", "Custom range"]
ALL_NYC = "All NYC"
ALL_FACTORS = "All factors"


def _complete_range(d: CrashData) -> tuple[int, int]:
    yrs = d.complete_years or d.years
    return min(yrs), max(yrs)


def init_state(d: CrashData) -> None:
    ss = st.session_state
    ss.setdefault("f_boroughs", [])
    ss.setdefault("f_year_mode", YEAR_MODES[0])
    ss.setdefault("f_years", _complete_range(d))
    ss.setdefault("f_factors", [])
    ss.setdefault("f_scope", "Vehicle 1 only")
    ss.setdefault("f_vehicles", [])
    ss.setdefault("f_severity", "All crashes")
    ss.setdefault("f_days", [])
    ss.setdefault("f_hours", (0, 23))
    ss.setdefault("f_filled", False)
    ss.setdefault("sel_cell", None)
    ss.setdefault("map_epoch", 0)
    ss.setdefault("last_pick", None)


def apply_pending() -> None:
    """Apply a map click stored before the last rerun.

    Must run BEFORE the sidebar widgets are created: Streamlit forbids changing
    a widget's session-state value after the widget exists in the run.
    """
    p = st.session_state.pop("pending", None)
    if not p:
        return
    if "borough" in p:
        st.session_state["f_boroughs"] = [p["borough"]]
        st.session_state["sel_cell"] = None
    if "cell" in p:
        st.session_state["sel_cell"] = p["cell"]


# ----------------------------------------------------------------- callbacks
def _bump_map() -> None:
    st.session_state["map_epoch"] += 1
    st.session_state["last_pick"] = None


def _reset(d: CrashData) -> None:
    ss = st.session_state
    ss["f_boroughs"] = []
    ss["f_year_mode"] = YEAR_MODES[0]
    ss["f_years"] = _complete_range(d)
    ss["f_factors"] = []
    ss["f_scope"] = "Vehicle 1 only"
    ss["f_vehicles"] = []
    ss["f_severity"] = "All crashes"
    ss["f_days"] = []
    ss["f_hours"] = (0, 23)
    ss["f_filled"] = False
    ss["sel_cell"] = None
    _bump_map()


def reset_filters(d: CrashData) -> None:
    _reset(d)


def clear_selection() -> None:
    st.session_state["sel_cell"] = None
    st.session_state["f_boroughs"] = []
    _bump_map()


def clear_cell() -> None:
    st.session_state["sel_cell"] = None
    _bump_map()


def _on_quick_borough() -> None:
    v = st.session_state.get("quick_boro")
    st.session_state["f_boroughs"] = [] if v in (None, ALL_NYC) else [v.upper()]
    st.session_state["sel_cell"] = None
    _bump_map()


def _on_quick_factor() -> None:
    v = st.session_state.get("quick_factor")
    st.session_state["f_factors"] = [] if v in (None, ALL_FACTORS) else [v]


# ----------------------------------------------------------------- quick selectors
def borough_quick(key: str = "quick_boro") -> None:
    """One-click borough buttons. Mirrors (and drives) the sidebar borough filter."""
    ss = st.session_state
    cur = ss["f_boroughs"]
    ss[key] = ALL_NYC if not cur else (borough_label(cur[0]) if len(cur) == 1 else None)
    st.segmented_control("Borough", [ALL_NYC] + [borough_label(b) for b in BOROUGHS], key=key,
                         on_change=_on_quick_borough, label_visibility="collapsed")


def factor_quick(options: list[str], key: str = "quick_factor") -> None:
    """One-click contributing-factor buttons (single factor). Mirrors the sidebar filter."""
    ss = st.session_state
    cur = ss["f_factors"]
    shown = [ALL_FACTORS] + list(options)
    if len(cur) == 1 and cur[0] not in shown:
        shown.append(cur[0])
    ss[key] = ALL_FACTORS if not cur else (cur[0] if len(cur) == 1 else None)
    st.segmented_control("Contributing factor", shown, key=key, on_change=_on_quick_factor,
                         label_visibility="collapsed")


# ----------------------------------------------------------------- sidebar
def render_sidebar(d: CrashData) -> tuple[Filters, str]:
    ss = st.session_state
    sb = st.sidebar
    head = sb.container()

    sb_heading("Where")
    sb.multiselect("Borough", BOROUGHS, key="f_boroughs", format_func=borough_label,
                   placeholder="All boroughs",
                   help="Or click a borough / hotspot on the map, or use the borough buttons above it.")
    if d.meta.get("has_filled_borough"):
        sb.checkbox("Fill missing boroughs from coordinates", key="f_filled",
                    help="~31% of rows have no borough. This assigns one from the crash's coordinates using "
                         "official borough boundaries. Off by default to match the original notebook.")

    sb_heading("When")
    sb.radio("Years", YEAR_MODES, key="f_year_mode",
             help=f"Partial years ({', '.join(map(str, sorted(d.partial_years)))}) do not cover all 12 months, "
                  "so they are left out of the default range.")
    lo, hi = min(d.years), max(d.years)
    if ss["f_year_mode"] == "Custom range":
        cur = ss["f_years"]
        ss["f_years"] = (max(lo, min(cur[0], hi)), max(lo, min(cur[1], hi)))
        sb.slider("Year range", lo, hi, key="f_years")
        years = tuple(ss["f_years"])
    elif ss["f_year_mode"] == YEAR_MODES[1]:
        years = (lo, hi)
    else:
        years = _complete_range(d)
    sb.multiselect("Day of week", list(range(7)), key="f_days", format_func=lambda i: DAY_NAMES[i],
                   placeholder="All days")
    sb.slider("Hour of day", 0, 23, key="f_hours", help="Inclusive: 7–9 means 7:00 through 9:59.")

    sb_heading("What")
    sb.multiselect("Contributing factor", d.factors, key="f_factors", placeholder="All factors",
                   help="As recorded by police. A recorded factor is not proof of cause.")
    if ss["f_factors"]:
        sb.radio("Match factor in", ["Vehicle 1 only", "Any vehicle in the crash"], key="f_scope",
                 help="Vehicle 1 only matches the original notebook. 'Any vehicle' uses all five factor "
                      "columns and still counts each crash once.")
    sb.multiselect("Vehicle type involved", d.vehicle_groups, key="f_vehicles",
                   placeholder="All vehicle types",
                   help="Crashes where at least one vehicle of this type is recorded. Says nothing about "
                        "which driver was at fault.")
    sb.radio("Crash severity", ["All crashes", "Injury crashes", "Fatal crashes"], key="f_severity",
             help="Drives the map and count charts. Rate charts and the two rate cards always use all severities.")

    years_label = "Years " + (f"{years[0]}–{years[1]}" if years[0] != years[1] else str(years[0]))
    f = Filters(
        boroughs=tuple(ss["f_boroughs"]),
        year_range=years,
        factors=tuple(ss["f_factors"]),
        factor_scope="any" if ss["f_scope"].startswith("Any") else "vehicle1",
        vehicles=tuple(ss["f_vehicles"]),
        severity={"All crashes": "all", "Injury crashes": "injury", "Fatal crashes": "fatal"}[ss["f_severity"]],
        days=tuple(ss["f_days"]),
        hour_range=tuple(ss["f_hours"]),
        use_filled_borough=bool(ss["f_filled"]) and bool(d.meta.get("has_filled_borough")),
        cell=tuple(ss["sel_cell"]) if ss["sel_cell"] else None,
    )

    with head:
        c1, c2 = st.columns([1.2, 1])
        c1.markdown("### Filters")
        c2.button("↺ Reset", on_click=_reset, args=(d,), key="reset_btn", width="stretch",
                  disabled=not (is_filtered(f) or ss["f_year_mode"] != YEAR_MODES[0]))
    sb.divider()
    sb.caption(f"Data: {d.meta['date_min']} → {d.meta['date_max']} · {d.n:,} crashes loaded")
    return f, years_label
