"""NYC Crash Explorer - Streamlit entry point.

Run:  streamlit run app.py
Needs data/processed/crashes.parquet (create it with scripts/prepare_data.py).

Two modes share the same data layer and filters:
  Explore  - sidebar filters + seven analysis tabs
  Present  - guided six-step, ~5-minute walkthrough (sidebar hidden)
"""
import streamlit as st

st.set_page_config(page_title="NYC Crash Explorer", page_icon="🚦", layout="wide",
                   initial_sidebar_state="expanded")

from components import filters as filters_ui          # noqa: E402
from components import present, sections, ui           # noqa: E402
from utils import cached                               # noqa: E402
from utils.data_helpers import is_filtered             # noqa: E402

SECTIONS = {
    "Overview": sections.overview,
    "Where": sections.where,
    "When": sections.when,
    "Factors": sections.factors,
    "Who": sections.who,
    "Compare": sections.compare,
    "Data & Methods": sections.methods,
}
MODES = ["Explore", "Present"]


def main() -> None:
    ss = st.session_state
    if ss.get("mode") not in MODES:
        ss["mode"] = "Explore"
    if ss.get("section") not in SECTIONS:
        ss["section"] = "Overview"
    present_mode = ss["mode"] == "Present"
    ui.inject_css(present=present_mode)

    head = st.columns([4.2, 1.5, 1.5], gap="small", vertical_alignment="center")
    with head[0]:
        st.markdown("<p class='app-title'>🚦 NYC Crash Explorer</p>"
                    "<p class='app-sub'>Interactive Analysis of New York City Motor Vehicle Collisions · "
                    "<i>Understanding Traffic Safety Through Data</i></p>", unsafe_allow_html=True)
    with head[1]:
        st.segmented_control("Mode", MODES, key="mode", label_visibility="collapsed",
                             help="Explore: filters + analysis tabs. Present: guided 5-minute walkthrough.")
    with head[2]:
        ui.glossary()

    if not cached.data_available():
        st.error("Processed data not found.")
        st.markdown("1. Put the Kaggle CSV in `data/raw/`\n"
                    "2. Run `python scripts/prepare_data.py`\n"
                    "3. Restart this app (`streamlit run app.py`)\n\nSee README.md for details.")
        st.stop()

    d = cached.load_data()
    filters_ui.init_state(d)
    filters_ui.apply_pending()                 # map clicks must be applied before widgets exist
    f, years_label = filters_ui.render_sidebar(d)   # also runs in Present mode (sidebar hidden by CSS) to keep state

    fkey = f.to_json()
    k = cached.kpis(d, fkey)
    if k["crashes"] == 0:
        st.markdown(ui.filter_chips(f, years_label), unsafe_allow_html=True)
        st.warning("No crashes match the current filters. Widen them or reset.")
        st.button("↺ Reset all filters", on_click=filters_ui.reset_filters, args=(d,), key="reset_empty")
        st.stop()
    kb = cached.baseline_kpis(d, fkey)

    st.markdown(ui.filter_chips(f, years_label), unsafe_allow_html=True)
    ui.kpi_cards(k, kb, f.severity, is_filtered(f))

    if present_mode:
        present.render(d, f, k, kb)
        return

    st.segmented_control("Section", list(SECTIONS), key="section", label_visibility="collapsed")
    SECTIONS[ss["section"]](d, f, k, kb)


main()
