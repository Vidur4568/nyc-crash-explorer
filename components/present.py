"""Presentation mode: a guided six-step, ~5-minute walk through the dashboard.

Same data layer, same filters and same charts as Explore mode; what changes is
the framing: one question per step, large visuals, live-demo controls (borough
buttons, factor buttons) and speaker notes whose numbers are computed from the
current selection. KPI cards stay on screen so the audience sees them update.
"""
from __future__ import annotations

import streamlit as st

from components import charts, sections
from components import filters as filters_ui
from components.ui import bullet, chart_card, fmt_int, fmt_pct
from utils import cached, insights as ins
from utils.schema import borough_label

STEPS = [
    ("The big picture", "How big is NYC's collision problem?", 30),
    ("Where", "Where do crashes occur?", 60),
    ("When", "When do they happen?", 60),
    ("Factors", "What factors are associated with severe collisions?", 70),
    ("Who", "Who is affected?", 40),
    ("Takeaways", "What should we take away — and what are the limits?", 40),
]
NAMES = [s[0] for s in STEPS]


def _go(delta: int = 0, to: int | None = None) -> None:
    ss = st.session_state
    step = to if to is not None else max(0, min(len(STEPS) - 1, ss["pstep"] + delta))
    ss["pstep"] = step
    ss["pstep_sel"] = NAMES[step]


def _on_select() -> None:
    v = st.session_state.get("pstep_sel")
    if v in NAMES:
        st.session_state["pstep"] = NAMES.index(v)


def _area(f) -> str:
    if f.cell:
        return "the selected hotspot"
    if f.boroughs:
        return " + ".join(borough_label(b) for b in f.boroughs)
    return "NYC overall"


# ----------------------------------------------------------------------------- notes
def _notes(step: int, d, f, k, kb) -> list[str]:
    v = ins.vs_city(k, kb)
    y0, y1 = f.year_range
    if step == 0:
        return [f"Open with the research question: where, when and under what circumstances are collisions most dangerous?",
                f"Scope: {fmt_int(k['crashes'])} police-reported crashes, {y0}–{y1}. Partial years are excluded so trends are fair.",
                f"Distinguish counts from rates: injury rate is {fmt_pct(k['injury_pct'])} — the share of crashes with ≥1 injury."]
    if step == 1:
        return ["Colour shows how many crashes were recorded, not how risky a place is.",
                "Demo: click a borough (or a borough button). The map zooms and every number above updates.",
                f"Now showing {_area(f)}: {fmt_int(k['crashes'])} crashes, {v['share_pct']:.1f}% of NYC's, "
                f"injury rate {fmt_pct(k['injury_pct'])} ({v['injury_pp']:+.1f} pp vs NYC)."]
    if step == 2:
        return ["Left: volume and severity by hour — the busiest hour is not always the most severe.",
                "Right: the weekly rhythm; switch the heatmap to injury rate to show severity.",
                "Mention the confidence band: late-night hours have fewer crashes, so rates are less certain."]
    if step == 3:
        return ["Say clearly: factors are what police recorded, not proven causes.",
                "Demo: click a factor button. KPI cards show the injury rate vs NYC; the map shows where it is recorded.",
                "Use the frequency-vs-severity view to point out factors that are both common and severe."]
    if step == 4:
        return ["Pedestrians, cyclists and motorists: counts of people injured, not rates.",
                "Vehicle chart: 'involves' does not mean 'at fault'.",
                "Without trip or traffic-volume data we cannot say which group is at greater risk per trip."]
    return ["Read the first two findings aloud; they are computed from the current selection.",
            "Be upfront about limits: missing boroughs, unspecified factors, no exposure data.",
            "Close with next steps: add population/traffic data and move from grid cells to street segments."]


# ----------------------------------------------------------------------------- slides
def _slide_big_picture(d, f, k, kb) -> None:
    fkey = f.to_json()
    yt = cached.year_table(d, fkey)
    a, b = st.columns([2.3, 1], gap="medium")
    with a:
        chart_card("Crashes per year",
                   "Police-reported collisions each year; open diamonds are partial years and are not comparable.",
                   charts.time_series_fig(yt, cached.month_table(d, fkey), "Annual", "crashes", f.year_range, height=340),
                   "p0_ts", why="sets the scale before we ask where, when and why.",
                   insight=ins.time_trend(yt, "crashes", "crashes"))
    with b:
        with st.container(border=True):
            st.markdown("<div class='ch-title'>How to read the numbers</div>", unsafe_allow_html=True)
            bullet("**Crashes** are collisions. More traffic means more crashes.", "good")
            bullet("**Injury rate** is the % of crashes with at least one injured person. It compares how *severe* "
                   "crashes are, whatever their number.", "good")
            bullet(f"Data covers **{d.meta['date_min']} → {d.meta['date_max']}**. Partial years are excluded by default.",
                   "warn")


def _slide_where(d, f, k, kb) -> None:
    fkey = f.to_json()
    s = sections.map_toolbar(full=False)
    a, b = st.columns([2.2, 1.15], gap="medium")
    with a:
        sections.map_view(d, f, k, s, height=470)
    with b:
        bt = cached.borough_table(d, fkey)
        chart_card("Total crashes by borough", "Crashes recorded in each borough (counts, not risk).",
                   charts.borough_crashes_fig(bt, f.boroughs, height=210), "p1_n", insight=ins.borough_counts(bt))
        chart_card("Injury rate by borough", "% of each borough's crashes with ≥1 injury; whiskers = 95% CI.",
                   charts.borough_rate_fig(bt, f.boroughs, height=210), "p1_r", insight=ins.borough_rates(bt))


def _slide_when(d, f, k, kb) -> None:
    fkey = f.to_json()
    ht = cached.hour_table(d, fkey)
    dh_ = cached.dow_hour_table(d, fkey)
    a, b = st.columns(2, gap="medium")
    with a:
        chart_card("Crash volume vs. injury rate by hour",
                   "Bars: crashes per hour. Red line: % of those crashes with ≥1 injury; band = 95% CI.",
                   charts.hour_fig(ht, f.hour_range, height=400), "p2_hour",
                   why="the busiest hour is not necessarily the most severe.", insight=ins.hour_profile(ht))
    with b:
        hm = st.segmented_control("Heatmap shows", ["Crash count", "Injury rate"], key="p_hm",
                                  default="Crash count") or "Crash count"
        chart_card("Weekly rhythm: day × hour",
                   f"{'Crashes' if hm == 'Crash count' else '% of crashes with ≥1 injury'} for each weekday and hour.",
                   charts.heatmap_fig(dh_, hm, height=340), "p2_hm", insight=ins.heatmap_peak(dh_))


def _slide_factors(d, f, k, kb) -> None:
    fkey = f.to_json()
    ft = cached.factor_table(d, fkey)
    overall = cached.overall_injury_rate(d, fkey)
    cov = cached.factor_coverage(d, fkey)
    # live-demo buttons: the three named factors plus the most frequent ones
    opts = [x for x in sections.DEFAULT_COMPARE if x in d.factors]
    for name in ft.sort_values("crashes", ascending=False)["factor"]:
        if len(opts) >= 5:
            break
        if name not in opts:
            opts.append(name)
    st.markdown("<div class='ch-sub'><b>Live demo:</b> pick a recorded factor — the KPI cards, charts and map all update "
                "(factors are police-recorded, not proven causes).</div>", unsafe_allow_html=True)
    filters_ui.factor_quick(opts)
    a, b = st.columns([1.1, 1], gap="medium")
    with a:
        view = st.segmented_control("Chart", ["Injury-rate ranking", "Frequency vs severity"], key="p_fac_view",
                                    default="Injury-rate ranking", label_visibility="collapsed") or "Injury-rate ranking"
        min_c = 500
        if view == "Injury-rate ranking":
            chart_card("Factors with the highest injury rates",
                       f"% of crashes with each factor in which ≥1 person was injured (factors with ≥{min_c} crashes).",
                       charts.factor_rate_fig(ft, overall, f.factors, min_c, height=400), "p3_rate",
                       insight=ins.factor_severity(ft, overall, min_c),
                       caveat="A high injury rate means crashes with this recorded factor more often involved injuries — "
                              "not that the factor caused them.")
        else:
            chart_card("Frequency vs. injury rate",
                       "Each dot is a factor: how often it is recorded (log scale) vs how often those crashes involved injury.",
                       charts.factor_scatter_fig(ft, overall, f.factors, min_c, height=400), "p3_scatter",
                       insight=ins.scatter_quadrant(ft, overall, min_c))
    with b:
        st.markdown("<div class='ch-title'>Where it is recorded</div>"
                    f"<div class='ch-sub'>Crash hotspots for {'the selected factor' if f.factors else 'all crashes'} "
                    f"({fmt_int(cov['with_factor'])} crashes have a specified factor).</div>", unsafe_allow_html=True)
        sections.map_view(d, f, k, sections.map_settings(), height=430, show_notes=False)


def _slide_who(d, f, k, kb) -> None:
    fkey = f.to_json()
    yt = cached.year_table(d, fkey)
    vt = cached.vehicle_table(d, fkey)
    overall = cached.overall_injury_rate(d, fkey, ex=("vehicle", "severity"))
    a, b = st.columns(2, gap="medium")
    with a:
        chart_card("People injured per year, by road-user type",
                   "Pedestrians, cyclists and motorists injured each year (people, not crashes).",
                   charts.road_user_fig(yt, height=480), "p4_users", insight=ins.road_users(yt),
                   caveat="Counts reflect how many people travel each way as well as danger; no trip data is included.")
    with b:
        chart_card("Injury rate of crashes involving each vehicle type",
                   "% of crashes involving each vehicle type with ≥1 injury; whiskers = 95% CI.",
                   charts.vehicle_rate_fig(vt, overall, f.vehicles, 500, height=480), "p4_veh",
                   insight=ins.vehicle_rates(vt, overall, 500),
                   caveat="'Involves' does not mean 'at fault'. A crash counts under every vehicle type it involves.")


def _slide_takeaways(d, f, k, kb) -> None:
    t = sections.tables_for(d, f)
    lines = ins.takeaways(t)
    a, b = st.columns(2, gap="large")
    with a:
        st.markdown(f"#### What the data shows · {_area(f)}")
        v = ins.vs_city(k, kb)
        if f.boroughs or f.factors or f.cell or f.vehicles:
            bullet(f"This selection is **{v['share_pct']:.1f}%** of NYC's crashes with an injury rate of "
                   f"**{fmt_pct(k['injury_pct'])}** ({v['injury_pp']:+.1f} pp vs NYC).", "good")
        for line in lines[:6]:
            bullet(line, "good")
    with b:
        st.markdown("#### Limits to keep in mind")
        for line in ins.limits(d.meta, k, t["bt"], t["factor_pct_with"]):
            bullet(line, "warn")
        st.markdown("#### Where this could go next")
        bullet("Add population and traffic-volume data to turn counts into true **risk rates**.", "good")
        bullet("Move from grid cells to **street segments and intersections** to pinpoint corridors.", "good")
        bullet("Test whether patterns survive after accounting for time, place and road type (statistical modelling).", "good")


SLIDES = [_slide_big_picture, _slide_where, _slide_when, _slide_factors, _slide_who, _slide_takeaways]


# ----------------------------------------------------------------------------- driver
def render(d, f, k, kb) -> None:
    ss = st.session_state
    ss.setdefault("pstep", 0)
    ss["pstep_sel"] = NAMES[ss["pstep"]]
    step = ss["pstep"]

    c = st.columns([6, 1, 1, 1.3], gap="small", vertical_alignment="center")
    with c[0]:
        st.segmented_control("Step", NAMES, key="pstep_sel", on_change=_on_select, label_visibility="collapsed")
    c[1].button("← Back", on_click=_go, kwargs={"delta": -1}, disabled=step == 0, key="p_back", width="stretch")
    c[2].button("Next →", on_click=_go, kwargs={"delta": 1}, disabled=step == len(STEPS) - 1, type="primary",
                key="p_next", width="stretch")
    with c[3]:
        with st.popover("🗒 Speaker notes"):
            for line in _notes(step, d, f, k, kb):
                st.markdown("- " + line)

    title, question, secs = STEPS[step]
    st.progress((step + 1) / len(STEPS), text=f"Step {step + 1} of {len(STEPS)} · about {secs} s")
    st.markdown(f"<div class='slide-title'>{step + 1}. {title}</div><div class='slide-q'>{question}</div>",
                unsafe_allow_html=True)
    SLIDES[step](d, f, k, kb)
