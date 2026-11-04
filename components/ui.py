"""Presentation helpers: theme CSS, KPI cards, self-explaining chart cards."""
from __future__ import annotations

import html
import math
import re
from typing import Optional

import streamlit as st

from utils.data_helpers import Filters
from utils.insights import vs_city
from utils.schema import DAY_NAMES, borough_label

PLOT_CONFIG = {"displayModeBar": False, "responsive": True}

CSS = """
<style>
  :root {
    --bg:#0B1220; --panel:#131C2E; --panel2:#101A2D; --line:#22304a; --text:#E6EDF7; --sub:#9FB0C8;
    --blue:#4EA8DE; --gold:#F5B841; --red:#EF476F; --green:#06D6A0;
  }
  .stApp {font-family: Inter, -apple-system, "Segoe UI", system-ui, sans-serif;}
  .block-container {padding-top: 3.1rem; padding-bottom: 2.5rem; max-width: 1560px;}
  [data-testid="stAppDeployButton"], .stAppDeployButton, [data-testid="stStatusWidget"] {display:none !important;}
  header[data-testid="stHeader"] {background: transparent;}
  h1,h2,h3,h4 {letter-spacing:-0.01em;}
  hr {margin: .6rem 0 !important; border-color: var(--line) !important;}

  /* header */
  .app-title {font-size:1.85rem; font-weight:760; margin:0; line-height:1.1;}
  .app-sub {color:var(--sub); margin:.2rem 0 .5rem 0; font-size:.96rem;}

  /* KPI cards */
  .kpi-grid {display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:.1rem 0 .7rem 0;}
  @media (max-width: 1150px) {.kpi-grid {grid-template-columns:repeat(3,minmax(0,1fr));}}
  .kpi {background:linear-gradient(180deg,#151f36,#111b2f); border:1px solid var(--line); border-left:3px solid var(--c);
        border-radius:12px; padding:9px 14px 8px 14px; min-height:96px;}
  .kpi .l {color:var(--sub); font-size:.70rem; text-transform:uppercase; letter-spacing:.07em; font-weight:600;}
  .kpi .v {font-size:1.7rem; font-weight:720; line-height:1.15; margin-top:1px;}
  .kpi .u {color:#7f93b3; font-size:.72rem; margin-top:-1px;}
  .kpi .d {font-size:.76rem; margin-top:3px; font-weight:600;}
  .d.up {color:var(--red);} .d.down {color:var(--green);} .d.flat, .d.na {color:var(--sub); font-weight:500;}

  /* chips */
  .chip {display:inline-block; padding:2px 10px; margin:0 6px 4px 0; border-radius:999px;
         background:#1b2a45; border:1px solid #2d4468; color:#cfe3ff; font-size:.78rem;}
  .chip.base {background:transparent; border-color:var(--line); color:var(--sub);}

  /* chart cards */
  .ch-title {font-size:1.02rem; font-weight:700; margin:0 0 1px 0;}
  .ch-sub {color:var(--sub); font-size:.84rem; line-height:1.35; margin-bottom:2px;}
  .ch-sub .why {color:#c9d6ea;}
  .ins {background:rgba(78,168,222,.10); border-left:3px solid var(--blue); border-radius:6px;
        padding:7px 11px; font-size:.86rem; color:#dbe6f7; margin:.2rem 0 .35rem 0; line-height:1.4;}
  .callout {background:var(--panel); border-left:3px solid var(--gold); padding:9px 13px; border-radius:6px;
            color:#cdd8ea; font-size:.86rem; margin:.3rem 0 .6rem 0;}
  .qline {color:var(--gold); font-size:.95rem; font-weight:600; margin:.1rem 0 .5rem 0;}
  .small {color:var(--sub); font-size:.8rem;}
  .tb-label {color:var(--sub); font-size:.7rem; text-transform:uppercase; letter-spacing:.07em; margin:0 0 -6px 2px; font-weight:600;}

  /* sidebar */
  [data-testid="stSidebar"] {background: var(--panel2); border-right:1px solid var(--line);}
  [data-testid="stSidebar"] .sb-h {color:var(--gold); font-size:.7rem; letter-spacing:.12em; font-weight:700;
        text-transform:uppercase; margin:.9rem 0 -.2rem 0;}

  /* slides */
  .slide-title {font-size:1.7rem; font-weight:760; margin:.2rem 0 0 0;}
  .slide-q {color:var(--sub); font-size:1.02rem; margin-bottom:.6rem;}
  .bullet {background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:9px 13px;
           margin-bottom:8px; font-size:.95rem; line-height:1.45;}
  .bullet.warn {border-left:3px solid var(--gold);}
  .bullet.good {border-left:3px solid var(--blue);}
</style>
"""

PRESENT_CSS = """
<style>
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"]
  {display:none !important;}
  .block-container {max-width: 1700px; padding-top: 2.4rem;}
  .kpi .v {font-size:1.95rem;}
  .ch-title {font-size:1.12rem;}
  .ch-sub, .ins {font-size:.92rem;}
</style>
"""


def inject_css(present: bool = False) -> None:
    st.markdown(CSS + (PRESENT_CSS if present else ""), unsafe_allow_html=True)


# ---------------------------------------------------------------- formatting
def fmt_int(x) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{int(round(x)):,}"


def fmt_pct(x, digits: int = 1) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}%"


def rich(text: str) -> str:
    """Escape HTML, then turn **bold** / *italic* markers into tags."""
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)


def callout(text: str) -> None:
    """`text` may contain trusted inline HTML (<b>, <i>)."""
    st.markdown(f"<div class='callout'>{text}</div>", unsafe_allow_html=True)


def qline(text: str) -> None:
    st.markdown(f"<div class='qline'>{html.escape(text)}</div>", unsafe_allow_html=True)


def sb_heading(text: str) -> None:
    st.sidebar.markdown(f"<div class='sb-h'>{text}</div>", unsafe_allow_html=True)


def tb_label(text: str) -> None:
    st.markdown(f"<div class='tb-label'>{text}</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- KPI cards
def _delta(value: float, unit: str, filtered: bool) -> str:
    if not filtered:
        return "<div class='d na'>NYC-wide</div>"
    if value is None or math.isnan(value):
        return "<div class='d na'>vs NYC: –</div>"
    if abs(value) < 0.05:
        return "<div class='d flat'>≈ NYC average</div>"
    cls = "up" if value > 0 else "down"
    arrow = "▲" if value > 0 else "▼"
    return f"<div class='d {cls}'>{arrow} {abs(value):.1f} {unit} vs NYC</div>"


def kpi_cards(k: dict, kb: dict, severity: str, filtered: bool) -> None:
    sev = {"all": "", "injury": " · injury crashes", "fatal": " · fatal crashes"}[severity]
    v = vs_city(k, kb)
    n = max(k["crashes"], 1)
    cards = [
        ("var(--blue)", "Crashes" + sev, fmt_int(k["crashes"]), "police-reported collisions",
         f"<div class='d na'>{v['share_pct']:.1f}% of NYC total</div>" if filtered
         else "<div class='d na'>NYC-wide</div>"),
        ("var(--gold)", "People injured", fmt_int(k["persons_injured"]), "people, not crashes",
         f"<div class='d na'>≈ {100 * k['persons_injured'] / n:.0f} per 100 crashes</div>"),
        ("var(--red)", "People killed", fmt_int(k["persons_killed"]), "people, not crashes",
         f"<div class='d na'>≈ {10000 * k['persons_killed'] / n:.0f} per 10,000 crashes</div>"),
        ("var(--red)", "Injury rate", fmt_pct(k["injury_pct"]), "% of crashes with ≥1 injury",
         _delta(v["injury_pp"], "pp", filtered)),
        ("var(--red)", "Fatality rate", fmt_pct(k["fatality_pct"], 2), "% of crashes with ≥1 death",
         _delta(v["fatality_pp"], "pp", filtered)),
    ]
    inner = "".join(
        f"<div class='kpi' style='--c:{c}' title='{html.escape(u)}'><div class='l'>{html.escape(l)}</div>"
        f"<div class='v'>{val}</div><div class='u'>{html.escape(u)}</div>{d}</div>"
        for c, l, val, u, d in cards)
    st.markdown(f"<div class='kpi-grid'>{inner}</div>", unsafe_allow_html=True)


def glossary() -> None:
    with st.popover("What do these numbers mean?"):
        st.markdown(
            "**Crash** – one police-reported collision (one row of data).  \n"
            "**People injured / killed** – the *number of people*; one crash can injure several.  \n"
            "**Injury rate** – the *percentage of crashes* in which at least one person was injured. "
            "It describes how severe crashes tend to be, not how many there are.  \n"
            "**Fatality rate** – the percentage of crashes in which at least one person died.  \n"
            "**pp** – percentage-point difference from the citywide figure for the same years.  \n\n"
            "Crash *counts* grow with traffic; *rates* compare severity. Neither measures personal risk "
            "without traffic or population data.")


# ---------------------------------------------------------------- chips
def filter_chips(f: Filters, years_label: str) -> str:
    chips = [f"<span class='chip base'>{years_label}</span>"]
    chips.append(f"<span class='chip'>{', '.join(borough_label(b) for b in f.boroughs)}</span>"
                 if f.boroughs else "<span class='chip base'>All boroughs</span>")
    if f.factors:
        scope = "any vehicle" if f.factor_scope == "any" else "vehicle 1"
        chips.append("<span class='chip'>Factor (" + scope + "): " + html.escape(", ".join(f.factors)) + "</span>")
    if f.vehicles:
        chips.append("<span class='chip'>Involves: " + html.escape(", ".join(f.vehicles)) + "</span>")
    if f.severity != "all":
        chips.append("<span class='chip'>" + {"injury": "Injury crashes", "fatal": "Fatal crashes"}[f.severity] + "</span>")
    if f.days:
        chips.append("<span class='chip'>" + ", ".join(DAY_NAMES[i][:3] for i in f.days) + "</span>")
    if tuple(f.hour_range) != (0, 23):
        chips.append(f"<span class='chip'>{f.hour_range[0]}:00–{f.hour_range[1]}:59</span>")
    if f.cell:
        chips.append(f"<span class='chip'>Map hotspot ≈{f.cell[0]} m cell</span>")
    return "".join(chips)


# ---------------------------------------------------------------- chart cards
def chart_card(title: str, measures: str, fig, key: str, *, why: Optional[str] = None,
               insight: Optional[str] = None, caveat: Optional[str] = None) -> None:
    """A figure with a title, a one-line 'what this measures', optional 'why it matters',
    a data-driven takeaway and a collapsible reading guide."""
    with st.container(border=True):
        sub = rich(measures)
        if why:
            sub += f" <span class='why'><b>Why it matters:</b> {rich(why)}</span>"
        st.markdown(f"<div class='ch-title'>{html.escape(title)}</div><div class='ch-sub'>{sub}</div>",
                    unsafe_allow_html=True)
        fig.update_layout(title=None, margin=dict(t=14))
        st.plotly_chart(fig, width="stretch", theme=None, key=key, config=PLOT_CONFIG)
        if insight:
            st.markdown(f"<div class='ins'>💡 {rich(insight)}</div>", unsafe_allow_html=True)
        if caveat:
            with st.popover("ⓘ How to read this · limits"):
                st.markdown(caveat)


def bullet(text: str, kind: str = "good") -> None:
    st.markdown(f"<div class='bullet {kind}'>{rich(text)}</div>", unsafe_allow_html=True)
