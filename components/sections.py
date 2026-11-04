"""Dashboard sections (Explore mode) and the reusable map panel.

Each section receives the loaded CrashData `d`, the current Filters `f`, the
headline numbers `k` for the selection and `kb` for the citywide baseline.
All heavy computation goes through utils.cached; all sentences shown to the
user come from utils.insights (computed from the same tables).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import streamlit as st

from components import charts, maps
from components import filters as filters_ui
from components.ui import (bullet, callout, chart_card, fmt_int, fmt_pct, qline, rich, tb_label)
from utils import cached, insights as ins
from utils.data_helpers import cell_center
from utils.schema import BOROUGHS, borough_label

BOUNDARY_PATH = cached.PROCESSED_DIR / "nyc_boroughs.geojson"
DEFAULT_COMPARE = ["Driver Inattention/Distraction", "Unsafe Speed", "Failure to Yield Right-of-Way"]

CLICK_BORO, CLICK_CELL = "Borough", "Hotspot cell"
METRICS = {"Crashes": "crashes", "Injury rate": "injury_rate", "Fatal crashes": "fatal_crashes"}
SIZES = {"100 m": 100, "250 m": 250, "500 m": 500, "1 km": 1000}


def _scope_label(f) -> str:
    return "any of the 5 vehicles" if f.factor_scope == "any" else "vehicle 1 only"


def _fix_none(key: str, default) -> None:
    """Segmented controls can be un-selected; always fall back to a valid value."""
    if st.session_state.get(key) is None:
        st.session_state[key] = default


def tables_for(d, f, min_c: int = 500) -> dict:
    """Aggregated tables used by insight text (all cached)."""
    fkey = f.to_json()
    cov = cached.factor_coverage(d, fkey)
    return {
        "bt": cached.borough_table(d, fkey), "ht": cached.hour_table(d, fkey),
        "dh": cached.dow_hour_table(d, fkey), "ft": cached.factor_table(d, fkey),
        "yt": cached.year_table(d, fkey), "with_factor": cov["with_factor"],
        "factor_pct_with": cov["pct_with_factor"], "overall": cached.overall_injury_rate(d, fkey),
        "min_c": min_c,
    }


# =============================================================================
# Map (toolbar + view), shared by Overview and Present mode
# =============================================================================
def map_toolbar(full: bool = True) -> dict:
    """Render the compact control row above the map and return the chosen settings."""
    ss = st.session_state
    boundary = maps.load_boroughs(str(BOUNDARY_PATH))
    ss.setdefault("map_metric", "Crashes")
    ss.setdefault("map_size", "250 m")
    ss.setdefault("click_mode", CLICK_BORO if boundary else CLICK_CELL)
    ss.setdefault("map_3d", False)
    ss.setdefault("map_min_n", 30)
    for key, default in (("map_metric", "Crashes"), ("map_size", "250 m"),
                         ("click_mode", CLICK_BORO if boundary else CLICK_CELL)):
        _fix_none(key, default)
    if not boundary and ss["click_mode"] == CLICK_BORO:
        ss["click_mode"] = CLICK_CELL

    if full:
        c = st.columns([2.9, 1.7, 1.5, 1.55, 0.6], gap="small")
    else:
        c = st.columns([3.2, 1.7, 0.1, 0.1, 0.1], gap="small")
    with c[0]:
        tb_label("Borough — zoom & filter")
        filters_ui.borough_quick()
    with c[1]:
        tb_label("Colour cells by")
        st.segmented_control("Colour by", list(METRICS), key="map_metric", label_visibility="collapsed",
                             help="Crashes = how many were recorded. Injury rate = % of crashes with ≥1 injury "
                                  "(cells with few crashes hidden). Fatal crashes = crashes with ≥1 death.")
    if full:
        with c[2]:
            tb_label("Cell size")
            st.segmented_control("Cell size", list(SIZES), key="map_size", label_visibility="collapsed",
                                 help="Smaller cells show finer detail but fewer crashes per cell.")
        with c[3]:
            tb_label("Click selects")
            if boundary:
                st.segmented_control("Click selects", [CLICK_BORO, CLICK_CELL], key="click_mode",
                                     label_visibility="collapsed")
            else:
                st.caption("Hotspot cell (add borough boundaries to click boroughs — see README)")
        with c[4]:
            tb_label("More")
            with st.popover("⚙"):
                st.toggle("3D columns", key="map_3d", help="Extrude cells by value (right-click drag to tilt).")
                st.slider("Min crashes per cell (rate view)", 10, 300, step=10, key="map_min_n",
                          help="Rates in cells with few crashes are very noisy, so those cells are hidden.")
    return map_settings()


def map_settings() -> dict:
    """Current map settings from session state (no widgets drawn)."""
    ss = st.session_state
    boundary = maps.load_boroughs(str(BOUNDARY_PATH))
    mode = ss.get("click_mode") or (CLICK_BORO if boundary else CLICK_CELL)
    if not boundary:
        mode = CLICK_CELL
    label = ss.get("map_metric") or "Crashes"
    return {"metric": METRICS[label], "metric_label": label,
            "size": SIZES[ss.get("map_size") or "250 m"], "click_mode": mode,
            "extruded": bool(ss.get("map_3d", False)), "min_n": int(ss.get("map_min_n", 30)),
            "boundary": boundary}


def map_view(d, f, k, s: dict, height: int = 560, show_notes: bool = True):
    """Draw the hotspot map, handle clicks, return the full (unfiltered-by-metric) grid."""
    fkey = f.to_json()
    boundary = s["boundary"]
    borough_mode = bool(boundary) and s["click_mode"] == CLICK_BORO
    g_all = cached.grid(d, fkey, s["size"])
    g = g_all
    if s["metric"] == "injury_rate":
        g = g_all[g_all["crashes"] >= s["min_n"]]
    elif s["metric"] == "fatal_crashes":
        g = g_all[g_all["fatal_crashes"] > 0]

    layers, line = [], None
    if boundary:
        bt = cached.borough_table(d, fkey)
        stats = {r.borough: (r.crashes, r.injury_rate) for r in bt.itertuples() if r.borough != "Unknown"}
        fill, line = maps.borough_layers(boundary, f.boroughs, pickable=borough_mode, stats=stats)
        layers.append(fill)
    cell_lyr, legend = maps.cell_layer(g, s["metric"], s["size"], s["extruded"], pickable=not borough_mode)
    layers += [cell_lyr, maps.selected_cell_layer(f.cell)]
    if line is not None:
        layers.append(line)
    deck = maps.make_deck(layers, maps.view_state(f.boroughs, s["extruded"], f.cell),
                          maps.BOROUGH_TOOLTIP if borough_mode else maps.CELL_TOOLTIP)
    event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object",
                            key=f"main_map_{st.session_state['map_epoch']}", height=height)

    if show_notes:
        a, b = st.columns([3, 1.2])
        with a:
            if legend:
                st.markdown(maps.legend_html(legend), unsafe_allow_html=True)
            else:
                st.info("No map cells for this selection — widen the filters or change the colour metric.")
        with b:
            with st.popover("ⓘ Reading the map"):
                geo_pct = k["pct_with_valid_coords"]
                st.markdown(
                    f"Each square is a **{s['size']} m** cell. The map shows {fmt_int(g_all['crashes'].sum())} "
                    f"crashes with valid coordinates in {len(g_all):,} cells; "
                    f"{fmt_pct(100 - geo_pct)} of crashes in this selection have no usable location.  \n\n"
                    "**Colour = how many crashes were recorded (or the share with injuries), not how risky a place "
                    "is.** Busy places record more crashes because more people travel there. "
                    + ("Click a borough to zoom and filter; switch 'Click selects' to pick a single cell."
                       if borough_mode else "Click a cell to zoom in and filter everything to it."))

    try:
        objs = dict(event.selection.get("objects", {}))
    except Exception:                                       # selection unavailable -> ignore clicks
        objs = {}
    pick = maps.decode_pick(objs)
    if pick and pick != st.session_state.get("last_pick"):
        st.session_state["last_pick"] = pick
        st.session_state["pending"] = pick
        st.rerun()
    return g_all


# =============================================================================
# Overview
# =============================================================================
def overview(d, f, k, kb) -> None:
    fkey = f.to_json()
    s = map_toolbar(full=True)
    left, right = st.columns([2.75, 1.1], gap="medium")
    with left:
        g_all = map_view(d, f, k, s, height=560)
        conc = ins.map_concentration(g_all)
        if conc:
            st.markdown(f"<div class='ins'>💡 {rich(conc)}</div>", unsafe_allow_html=True)
    with right:
        spotlight(d, f, k, kb)

    with st.expander("Top 10 hotspot cells for the current selection"):
        top = g_all.sort_values("crashes", ascending=False).head(10)
        if top.empty:
            st.write("No geocoded crashes.")
        else:
            t = pd.DataFrame({
                "Cell centre (lat, lon)": [f"{a:.4f}, {b:.4f}" for a, b in zip(top["lat"], top["lon"])],
                "Crashes": top["crashes"].astype(int),
                "Injury rate %": top["injury_rate"].round(1),
                "Fatal crashes": top["fatal_crashes"].astype(int),
                "Map": [f"https://www.google.com/maps?q={a:.5f},{b:.5f}" for a, b in zip(top["lat"], top["lon"])],
            })
            st.dataframe(t, hide_index=True, width="stretch",
                         column_config={"Map": st.column_config.LinkColumn("Map", display_text="open")})
            st.caption("Cells are squares, not street segments. Ranking raw counts mostly surfaces the busiest roads.")

    st.markdown("#### Borough comparison")
    _borough_cards(d, f, key="ov")
    _takeaways(d, f)


def spotlight(d, f, k, kb) -> None:
    fkey = f.to_json()
    if f.cell:
        title = "Selected hotspot"
    elif f.boroughs:
        title = " + ".join(borough_label(b) for b in f.boroughs)
    else:
        title = "Citywide"
    v = ins.vs_city(k, kb)
    with st.container(border=True):
        st.markdown(f"<div class='ch-title'>Area spotlight · {title}</div>"
                    "<div class='ch-sub'>Follows every filter. Comparison is against NYC for the same years.</div>",
                    unsafe_allow_html=True)
        if f.boroughs or f.cell or f.factors or f.vehicles or f.days or f.severity != "all" or f.hour_range != (0, 23):
            arrow = "▲" if v["injury_pp"] > 0 else "▼"
            bullet(f"**{v['share_pct']:.1f}%** of NYC's crashes · injury rate **{fmt_pct(k['injury_pct'])}** "
                   f"({arrow} {abs(v['injury_pp']):.1f} pp vs NYC)", "good")
        ft = cached.factor_table(d, fkey)
        top = ft.sort_values("crashes", ascending=False).head(5)
        st.markdown(f"**Top recorded factors** <span class='small'>({_scope_label(f)}, excl. Unspecified)</span>",
                    unsafe_allow_html=True)
        if top["crashes"].sum() == 0:
            st.caption("No factor data in this selection.")
        else:
            st.dataframe(pd.DataFrame({"Factor": top["factor"], "Crashes": top["crashes"].astype(int),
                                       "Injury %": top["injury_rate"].round(1)}),
                         hide_index=True, width="stretch", height=213)
        ht = cached.hour_table(d, fkey)
        if ht["crashes"].sum() > 0:
            busiest = ht.sort_values("crashes", ascending=False).head(3)["hour"].tolist()
            st.markdown("**Busiest hours:** " + ", ".join(f"{h}:00" for h in busiest))
            dang = ht[ht["inj_known"] >= 100].sort_values("injury_rate", ascending=False).head(3)
            if len(dang):
                st.markdown("**Highest injury-rate hours:** " + ", ".join(
                    f"{int(h)}:00 ({r:.0f}%)" for h, r in zip(dang["hour"], dang["injury_rate"])))
        if f.cell:
            size, ix, iy = f.cell
            lat, lon = cell_center(ix, iy, size)
            st.caption(f"Cell centre {float(lat):.4f}, {float(lon):.4f} · {size} m square")
            st.button("✕ Clear hotspot", on_click=filters_ui.clear_cell, key="clr_cell", width="stretch")
        elif f.boroughs:
            st.button("✕ Show all NYC", on_click=filters_ui.clear_selection, key="clr_boro", width="stretch")
        else:
            st.caption("Click a borough or cell on the map to zoom in on it.")


def _borough_cards(d, f, key: str) -> None:
    fkey = f.to_json()
    bt = cached.borough_table(d, fkey)
    tot, unk = bt["crashes"].sum(), bt.loc[bt["borough"] == "Unknown", "crashes"].sum()
    unk_txt = (f"{100 * unk / tot:.0f}% of crashes here have no recorded borough and are not shown. "
               "Borough totals therefore understate every borough." if tot else "")
    a, b = st.columns(2)
    with a:
        chart_card("Total crashes by borough",
                   "Number of police-reported crashes recorded in each borough (counts, not risk).",
                   charts.borough_crashes_fig(bt, f.boroughs), f"{key}_boro_n",
                   why="shows where crash activity is concentrated — larger boroughs with more traffic record more.",
                   insight=ins.borough_counts(bt), caveat=unk_txt)
    with b:
        chart_card("Injury rate by borough",
                   "Percent of each borough's crashes in which at least one person was injured. "
                   "Whiskers are 95% confidence intervals.",
                   charts.borough_rate_fig(bt, f.boroughs), f"{key}_boro_rate",
                   why="compares how severe crashes tend to be, regardless of how many occur.",
                   insight=ins.borough_rates(bt),
                   caveat="A rate needs a denominator: crashes with a recorded injury count. It is not the chance "
                          "that a person is hurt. " + unk_txt)


def _takeaways(d, f) -> None:
    t = tables_for(d, f)
    lines = ins.takeaways(t)
    if lines:
        with st.expander("Key takeaways for the current selection (auto-generated)"):
            for line in lines:
                bullet(line, "good")
            callout("Descriptive summaries of recorded crashes — not causes, and not risk without traffic or "
                    "population data. Missing boroughs and unspecified factors are excluded from the statements.")


# =============================================================================
# Where
# =============================================================================
def where(d, f, k, kb) -> None:
    fkey = f.to_json()
    qline("Where do crashes occur?")
    _borough_cards(d, f, key="w")
    bt = cached.borough_table(d, fkey)
    tot = bt["crashes"].sum()
    unk = bt.loc[bt["borough"] == "Unknown", "crashes"].sum()
    callout(f"<b>{fmt_pct(100 * unk / tot if tot else float('nan'))} of crashes in this selection have no "
            "recorded borough</b> and are left out of the charts above; the table below includes them so totals "
            "reconcile. " + ("Use the sidebar option to fill boroughs from crash coordinates."
                             if d.meta.get("has_filled_borough") else
                             "Run scripts/download_boundaries.py and re-run prepare_data.py to fill them from coordinates."))
    t = bt.copy()
    show_df = pd.DataFrame({
        "Borough": [borough_label(x) for x in t["borough"]], "Crashes": t["crashes"].astype(int),
        "Share %": (100 * t["crashes"] / tot).round(1) if tot else np.nan,
        "Injury crashes": t["injury_crashes"].astype(int), "Injury rate %": t["injury_rate"].round(2),
        "95% CI": [("–" if np.isnan(l) else f"{l:.1f}–{h:.1f}") for l, h in zip(t["ci_low"], t["ci_high"])],
        "People injured": t["persons_injured"].astype(int), "People killed": t["persons_killed"].astype(int),
    })
    st.dataframe(show_df, hide_index=True, width="stretch")
    st.caption("Raw totals: boroughs differ hugely in population, road length and traffic. Population- or "
               "traffic-adjusted rates would need external data (e.g. Census population, NYC DOT traffic counts).")


# =============================================================================
# When
# =============================================================================
def when(d, f, k, kb) -> None:
    fkey = f.to_json()
    qline("When do crashes occur?")
    c1, c2 = st.columns([1, 2.4])
    mode = c1.segmented_control("Time resolution", ["Annual", "Monthly"], key="ts_mode", default="Annual") or "Annual"
    metric = c2.segmented_control("Measure", list(charts.METRIC_LABELS), key="ts_metric", default="crashes",
                                  format_func=lambda m: charts.METRIC_LABELS[m]) or "crashes"
    label = charts.METRIC_LABELS[metric].lower()
    yt = cached.year_table(d, fkey)
    fig = charts.time_series_fig(yt, cached.month_table(d, fkey), mode, metric, f.year_range)
    chart_card(f"{charts.METRIC_LABELS[metric]} over time",
               f"Number of {label} per {'year' if mode == 'Annual' else 'month'}; the shaded band is your selected years.",
               fig, "when_ts", why="shows whether the problem is growing or shrinking. Only complete years are comparable.",
               insight=ins.time_trend(yt, metric, label) if mode == "Annual" else None,
               caveat="Open diamonds are partial years (they do not cover 12 months) and should not be compared with "
                      "full years. Recording practices, traffic patterns and events (e.g. the 2020 pandemic period) all "
                      "change over time, so the data alone cannot explain a trend.")
    ht = cached.hour_table(d, fkey)
    a, b = st.columns(2)
    with a:
        chart_card("Crash volume vs. injury rate by hour",
                   "Bars: crashes per hour (left axis). Red line: % of those crashes with ≥1 injury (right axis); "
                   "the band is a 95% confidence interval.",
                   charts.hour_fig(ht, f.hour_range, height=360), "when_hour",
                   why="the busiest hour is not necessarily when crashes are most severe.",
                   insight=ins.hour_profile(ht),
                   caveat="Late-night hours have few crashes, so their rates are less certain (wider band). Hours are "
                          "taken from the recorded crash time.")
    with b:
        hm = st.segmented_control("Heatmap shows", ["Crash count", "Injury rate"], key="hm_metric",
                                  default="Crash count") or "Crash count"
        dh_ = cached.dow_hour_table(d, fkey)
        chart_card("Weekly rhythm: day × hour",
                   f"{'Number of crashes' if hm == 'Crash count' else '% of crashes with ≥1 injury'} for every "
                   "weekday and hour combination.",
                   charts.heatmap_fig(dh_, hm, height=330), "when_hm",
                   why="reveals commute peaks, weekend nights and other weekly patterns.",
                   insight=ins.heatmap_peak(dh_),
                   caveat="In the rate view, slots with fewer than 30 crashes are hidden because their percentages "
                          "are unreliable.")


# =============================================================================
# Factors
# =============================================================================
def factors(d, f, k, kb) -> None:
    fkey = f.to_json()
    qline("What factors are associated with crashes?")
    cov = cached.factor_coverage(d, fkey)
    callout(f"Factors are <b>as recorded by police</b>, not proof of cause. Counting <b>{_scope_label(f)}</b> "
            "(choose a factor in the sidebar to switch to 'any vehicle'). "
            f"<b>{fmt_pct(100 - cov['pct_with_factor'])}</b> of crashes here are 'Unspecified' or blank and are excluded.")
    ft = cached.factor_table(d, fkey)
    overall = cached.overall_injury_rate(d, fkey)
    min_c = st.slider("Minimum crashes for a factor to appear in the rate charts", 50, 5000, 500, 50, key="fac_min",
                      help="The original notebook used 1,000. Lower values include rarer factors whose rates are "
                           "less reliable (see the whiskers).")
    a, b = st.columns(2)
    with a:
        chart_card("Most frequently recorded factors",
                   f"Number of crashes in which each factor was recorded ({_scope_label(f)}), excluding 'Unspecified'.",
                   charts.top_factors_fig(ft, f.factors, scope_label=_scope_label(f)), "fac_top",
                   why="shows what officers record most often — which depends on what they can observe at the scene.",
                   insight=ins.factor_frequency(ft, cov["with_factor"]))
    with b:
        chart_card("Factors with the highest injury rates",
                   f"Percent of crashes with each factor in which ≥1 person was injured (factors with ≥{min_c:,} crashes). "
                   "Whiskers are 95% confidence intervals.",
                   charts.factor_rate_fig(ft, overall, f.factors, min_c), "fac_rate",
                   why="separates factors that are common from those associated with more severe outcomes.",
                   insight=ins.factor_severity(ft, overall, min_c),
                   caveat="A high injury rate means crashes with this recorded factor more often involved injuries. "
                          "It does not mean the factor caused the injuries; vehicle speed, location and who is involved "
                          "also differ between factors.")
    chart_card("Frequency vs. injury rate, by contributing factor",
               "Each dot is a factor: how often it is recorded (x, log scale) against how often those crashes involved injury (y).",
               charts.factor_scatter_fig(ft, overall, f.factors, min_c), "fac_scatter",
               why="highlights factors that are both common and associated with severe crashes — the best candidates for attention.",
               insight=ins.scatter_quadrant(ft, overall, min_c),
               caveat="In 'any vehicle' mode a crash is counted once per factor but can appear under several factors, so "
                      "dot counts do not sum to the number of crashes.")


# =============================================================================
# Who
# =============================================================================
def who(d, f, k, kb) -> None:
    fkey = f.to_json()
    qline("Who is affected?")
    yt = cached.year_table(d, fkey)
    chart_card("People injured per year, by road-user type",
               "Number of pedestrians, cyclists and motorists injured each year (people, not crashes). "
               "Open diamonds are partial years.",
               charts.road_user_fig(yt), "who_users",
               why="shows whether the burden is shifting between ways of travelling.",
               insight=ins.road_users(yt),
               caveat="These are counts. They reflect how many people travel each way as well as how dangerous crashes "
                      "are; the dataset has no trip or mileage data. Each panel has its own y-axis.")
    vt = cached.vehicle_table(d, fkey)
    overall = cached.overall_injury_rate(d, fkey, ex=("vehicle", "severity"))
    min_c = st.slider("Minimum crashes for a vehicle group to appear", 50, 5000, 500, 50, key="veh_min")
    chart_card("Injury rate of crashes involving each vehicle type",
               "Percent of crashes involving each vehicle type in which ≥1 person was injured. Whiskers: 95% CI.",
               charts.vehicle_rate_fig(vt, overall, f.vehicles, min_c), "who_veh",
               why="vulnerable and heavy vehicles can be associated with different crash outcomes.",
               insight=ins.vehicle_rates(vt, overall, min_c),
               caveat="A crash counts under every vehicle type it involves, so bars overlap. 'Involves' does not mean "
                      "'at fault'. Types are grouped from free-text entries by keyword rules (see Data & Methods).")


# =============================================================================
# Compare
# =============================================================================
def compare(d, f, k, kb) -> None:
    fkey = f.to_json()
    qline("How do factors and boroughs differ?")
    mode = st.segmented_control("View", ["Factor geography", "Borough vs borough"], key="cmp_mode",
                                default="Factor geography") or "Factor geography"
    if mode == "Factor geography":
        _compare_factors(d, f, fkey)
    else:
        _compare_boroughs(d, f, fkey)


def _compare_factors(d, f, fkey) -> None:
    defaults = [x for x in DEFAULT_COMPARE if x in d.factors]
    c1, c2, c3 = st.columns([2.2, 1.6, 1])
    sel = c1.multiselect("Factors to compare (up to 3)", d.factors, default=defaults, max_selections=3,
                         key="cmp_factors")
    view = c2.segmented_control("Map shows", ["Where they occur", "Over/under-represented"], key="cmp_view",
                                default="Where they occur",
                                help="'Where they occur' = crash counts. 'Over/under-represented' = a cell's share of "
                                     "this factor's crashes ÷ its share of ALL crashes, which removes general crash volume."
                                ) or "Where they occur"
    size = c3.select_slider("Cell size (m)", [250, 500, 1000], value=500, key="cmp_size")
    if not sel:
        st.info("Pick at least one contributing factor.")
        return
    min_total = 30 if size == 250 else 60 if size == 500 else 100
    cols = st.columns(len(sel), gap="small")
    for col, fac in zip(cols, sel):
        with col:
            fk = replace(f, factors=(fac,), cell=None).to_json()
            if view == "Where they occur":
                g = cached.grid(d, fk, int(size), ex=("cell", "severity"))
                lyr, leg = maps.cell_layer(g, "crashes", int(size), pickable=True)
                tip = maps.CELL_TOOLTIP
                note = f"{fmt_int(int(g['crashes'].sum()) if len(g) else 0)} geocoded crashes"
            else:
                g = cached.over_representation(d, fkey, fac, int(size), min_total)
                lyr, leg = maps.cell_layer(g, "ratio", int(size), pickable=True)
                tip = maps.RATIO_TOOLTIP
                note = f"{len(g):,} cells with ≥{min_total} crashes"
            st.markdown(f"**{fac}**")
            if lyr is None:
                st.info("No data for this selection.")
                continue
            deck = maps.make_deck([lyr], maps.view_state(f.boroughs), tip)
            st.pydeck_chart(deck, key=f"cmp_map_{fac}_{view}_{size}", height=430)
            st.markdown(maps.legend_html(leg), unsafe_allow_html=True)
            st.caption(note)
    callout("Each map uses its own colour scale, so compare <i>patterns</i>, not colours. Raw counts mostly "
            "reproduce where all crashes happen; the over/under-represented view shows where a factor is "
            "<i>disproportionately</i> recorded. That is descriptive: it may reflect road design, enforcement "
            "or police reporting habits rather than driver behaviour.")


def _compare_boroughs(d, f, fkey) -> None:
    c1, c2 = st.columns(2)
    a_name = c1.selectbox("Borough A", BOROUGHS, index=BOROUGHS.index("BROOKLYN"), format_func=borough_label, key="cmp_a")
    b_name = c2.selectbox("Borough B", BOROUGHS, index=BOROUGHS.index("MANHATTAN"), format_func=borough_label, key="cmp_b")
    A, B = cached.area_tables(d, fkey, a_name), cached.area_tables(d, fkey, b_name)
    la, lb = borough_label(a_name), borough_label(b_name)
    rows = [("Crashes", "crashes", fmt_int), ("People injured", "persons_injured", fmt_int),
            ("People killed", "persons_killed", fmt_int), ("Injury rate (% of crashes)", "injury_pct", fmt_pct),
            ("Fatality rate (% of crashes)", "fatality_pct", lambda v: fmt_pct(v, 2))]
    st.dataframe(pd.DataFrame({"Measure": [r[0] for r in rows],
                               la: [r[2](A["kpi"][r[1]]) for r in rows],
                               lb: [r[2](B["kpi"][r[1]]) for r in rows]}),
                 hide_index=True, width="stretch")
    x, y = st.columns(2)
    with x:
        chart_card("When crashes happen, side by side",
                   "Share of each borough's own crashes that occur in each hour.",
                   charts.compare_hour_fig(A["hour"], B["hour"], la, lb), "cmp_hour",
                   why="normalising by each borough's total compares the *shape* of the day, not its size.")
    with y:
        chart_card("Top contributing factors, side by side",
                   "Share of each borough's crashes (with a specified factor) that record each factor.",
                   charts.compare_factor_fig(A["factor"], B["factor"], la, lb), "cmp_fac",
                   why="shows whether the mix of recorded factors differs between boroughs.")
    st.caption("Uses your other sidebar filters (years, factor, vehicle, day, hour) but ignores the borough and "
               "severity filters. Boroughs differ in size and traffic, so compare shapes and rates rather than raw counts.")


# =============================================================================
# Data & methods
# =============================================================================
def methods(d, f, k, kb) -> None:
    m, q = d.meta, d.meta["quality"]
    qline("How was this built, and what are its limits?")
    st.markdown(f"""
**Source:** NYC Motor Vehicle Collisions – Crashes (NYPD via NYC Open Data), as packaged on Kaggle
(`Motor_Vehicle_Collisions_-_Crashes_20250603.csv`). **Coverage in this file: {m['date_min']} to {m['date_max']}.**
Partial years: **{', '.join(map(str, m['partial_years']))}** (excluded from the default year range and flagged on charts).

**Definitions**
- **Crash** = one row (one `COLLISION_ID`). **Injury crash** = crash with ≥1 person injured. **People injured** = sum of
  persons injured. These are different numbers.
- **Injury rate** = injury crashes ÷ crashes whose injury count is recorded (missing counts are *not* treated as zero).
  Shown with 95% Wilson confidence intervals where space allows.
- **Contributing factor** = what police recorded for a vehicle; not proof of cause. 'Unspecified', blank and numeric
  junk codes are excluded. 'Vehicle 1 only' matches the original notebook; 'Any vehicle' counts each crash once per factor.
- **Vehicle type** = free text grouped by keyword rules into {len(d.vehicle_groups)} groups. 'Involves' ≠ 'at fault'.
- **Map** = squares of 100 m–1 km aggregated from valid coordinates inside a rectangle around NYC. Density ≠ risk.
- **Comparison with NYC** (KPI cards, spotlight) = the same years with every other filter cleared.

**Not included (needs outside data):** population-, traffic-volume- or mileage-adjusted rates; street-level geometry;
road design, speed limits or enforcement data. Borough boundaries (clicking and optional borough filling)
come from NYC Department of City Planning "Borough Boundaries (Clipped to Shoreline)".
""")
    st.markdown("#### Data-quality report (from the prep step)")
    qa = pd.DataFrame([
        ("Rows in raw file", fmt_int(q["rows_raw"])),
        ("Duplicate COLLISION_IDs dropped", fmt_int(q["duplicate_collision_ids_dropped"])),
        ("Rows dropped (unparseable date)", fmt_int(q["rows_dropped_bad_date"])),
        ("Rows used", fmt_int(q["rows_final"])),
        ("Borough missing", fmt_pct(q["borough_missing_pct"])),
        ("Valid coordinates", fmt_pct(q["coords_valid_pct"])),
        ("Coordinates present but invalid (e.g. 0,0)", fmt_int(q["coords_present_but_invalid"])),
        ("Injury count missing (rows)", fmt_int(q["persons_injured_missing"])),
        ("Fatality count missing (rows)", fmt_int(q["persons_killed_missing"])),
        ("Vehicle-1 factor usable", fmt_pct(q["factor1_usable_pct"])),
        ("Vehicle-type entries grouped as 'Other'", fmt_pct(q["vehicle_other_group_share_pct"])),
    ], columns=["Check", "Result"])
    st.dataframe(qa, hide_index=True, width="stretch")
    yrs = pd.DataFrame({
        "Year": m["years"],
        "Crashes": [q["crashes_per_year"].get(str(y), q["crashes_per_year"].get(y, 0)) for y in m["years"]],
        "Partial year": ["yes" if y in d.partial_years else "" for y in m["years"]],
        "Borough missing %": [q["borough_missing_pct_by_year"].get(str(y), q["borough_missing_pct_by_year"].get(y))
                              for y in m["years"]],
    })
    st.dataframe(yrs, hide_index=True, width="stretch")
    st.caption("If 'Borough missing %' changes a lot between years, borough comparisons across years are not like-for-like.")
    with st.expander("Vehicle-type grouping audit (most common raw values)"):
        st.dataframe(pd.DataFrame(m["vehicle_audit_top40"]), hide_index=True, width="stretch")
