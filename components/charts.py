"""Plotly figure builders. Each function takes an already-aggregated DataFrame
(from utils.data_helpers) and returns a `go.Figure`. No data crunching here."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.schema import DAY_NAMES, borough_label

C = {
    "primary": "#4EA8DE", "accent": "#F5B841", "danger": "#EF476F", "good": "#06D6A0",
    "muted": "#43536D", "text": "#E6EDF7", "subtle": "#9FB0C8", "grid": "rgba(255,255,255,0.08)",
    "panel": "#131C2E",
}


def short(label: str, n: int = 40) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def style(fig: go.Figure, height: int = 380, title: Optional[str] = None,
          legend: bool = False) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, Segoe UI, sans-serif", color=C["text"], size=12),
        margin=dict(l=8, r=8, t=48 if title else 16, b=8),
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)) if title else None,
        hoverlabel=dict(bgcolor=C["panel"], font_size=12, bordercolor=C["muted"]),
        bargap=0.28,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(gridcolor=C["grid"], zeroline=False, linecolor=C["grid"])
    fig.update_yaxes(gridcolor=C["grid"], zeroline=False, linecolor=C["grid"])
    return fig


def empty_fig(message: str = "No crashes match the current filters", height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color=C["subtle"]))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style(fig, height)


def _colors(names, selected: Sequence[str], base: str):
    """Semantic bar colours: `base` normally; gold for the selection, dimmed for the rest."""
    if not selected:
        return [base] * len(names)
    return [C["accent"] if n in selected else C["muted"] for n in names]


def _ci_arrays(df: pd.DataFrame):
    return dict(type="data", symmetric=False,
                array=(df["ci_high"] - df["injury_rate"]).to_numpy(),
                arrayminus=(df["injury_rate"] - df["ci_low"]).to_numpy(),
                color=C["subtle"], thickness=1.2, width=3)


# ---------------------------------------------------------------- Section A: Where
def borough_crashes_fig(df: pd.DataFrame, selected: Sequence[str] = (), height: int = 360) -> go.Figure:
    d = df[df["borough"] != "Unknown"].sort_values("crashes", ascending=False)
    if d["crashes"].sum() == 0:
        return empty_fig(height=height)
    colors = _colors(list(d["borough"]), selected, C["primary"])
    fig = go.Figure(go.Bar(
        x=[borough_label(b) for b in d["borough"]], y=d["crashes"], marker_color=colors,
        text=[f"{v:,.0f}" for v in d["crashes"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{y:,.0f} crashes<extra></extra>"))
    fig.update_yaxes(title="Crashes", rangemode="tozero")
    return style(fig, height, "Total crashes by borough")


def borough_rate_fig(df: pd.DataFrame, selected: Sequence[str] = (), height: int = 360) -> go.Figure:
    d = df[(df["borough"] != "Unknown") & (df["inj_known"] > 0)].sort_values("injury_rate", ascending=False)
    if d.empty:
        return empty_fig(height=height)
    colors = _colors(list(d["borough"]), selected, C["danger"])
    fig = go.Figure(go.Bar(
        x=[borough_label(b) for b in d["borough"]], y=d["injury_rate"], marker_color=colors,
        error_y=_ci_arrays(d),
        text=[f"{v:.1f}%" for v in d["injury_rate"]], textposition="outside", cliponaxis=False,
        customdata=np.column_stack([d["injury_crashes"], d["inj_known"], d["ci_low"], d["ci_high"]]),
        hovertemplate=("<b>%{x}</b><br>Injury rate: %{y:.2f}%<br>95%% CI: %{customdata[2]:.2f}–%{customdata[3]:.2f}%"
                       "<br>%{customdata[0]:,.0f} injury crashes of %{customdata[1]:,.0f}<extra></extra>")))
    fig.update_yaxes(title="Crashes with ≥1 injury (%)", rangemode="tozero")
    return style(fig, height, "Injury rate by borough (% of crashes with ≥1 injured person)")


# ---------------------------------------------------------------- Section B: When
METRIC_LABELS = {
    "crashes": "Crashes", "injury_crashes": "Crashes with ≥1 injury",
    "persons_injured": "Persons injured", "persons_killed": "Persons killed",
}


def time_series_fig(df_year: pd.DataFrame, df_month: pd.DataFrame, mode: str = "Annual",
                    metric: str = "crashes", year_range: Optional[tuple] = None,
                    height: int = 400) -> go.Figure:
    label = METRIC_LABELS[metric]
    fig = go.Figure()
    if mode == "Annual":
        if df_year["crashes"].sum() == 0:
            return empty_fig(height=height)
        comp = df_year[~df_year["partial"]]
        part = df_year[df_year["partial"]]
        fig.add_trace(go.Scatter(
            x=comp["year"], y=comp[metric], mode="lines+markers", name="Complete year",
            line=dict(color=C["primary"], width=3), marker=dict(size=8),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f}<extra></extra>"))
        if len(part):
            fig.add_trace(go.Scatter(
                x=part["year"], y=part[metric], mode="markers", name="Partial year (not comparable)",
                marker=dict(size=11, symbol="diamond-open", color=C["accent"], line=dict(width=2)),
                hovertemplate="<b>%{x} (partial year)</b><br>%{y:,.0f}<extra></extra>"))
        if year_range:
            fig.add_vrect(x0=year_range[0] - 0.5, x1=year_range[1] + 0.5,
                          fillcolor=C["primary"], opacity=0.07, line_width=0)
        fig.update_xaxes(dtick=1, title="Year")
    else:
        if df_month.empty:
            return empty_fig(height=height)
        fig.add_trace(go.Scatter(
            x=df_month["month_start"], y=df_month[metric], mode="lines", name=label,
            line=dict(color=C["primary"], width=2),
            hovertemplate="<b>%{x|%b %Y}</b><br>%{y:,.0f}<extra></extra>"))
        if year_range:
            fig.add_vrect(x0=f"{year_range[0]}-01-01", x1=f"{year_range[1]}-12-31",
                          fillcolor=C["primary"], opacity=0.07, line_width=0)
        fig.update_xaxes(title="Month")
    fig.update_yaxes(title=label, rangemode="tozero")
    return style(fig, height, f"{label} over time ({mode.lower()})", legend=(mode == "Annual"))


def hour_fig(df: pd.DataFrame, hour_range: tuple = (0, 23), height: int = 400) -> go.Figure:
    if df["crashes"].sum() == 0:
        return empty_fig(height=height)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    sel = [(hour_range[0] <= h <= hour_range[1]) for h in df["hour"]]
    fig.add_trace(go.Bar(
        x=df["hour"], y=df["crashes"], name="Crashes (left axis)",
        marker_color=[C["muted"] if s else "rgba(67,83,109,0.35)" for s in sel],
        hovertemplate="Hour %{x}:00<br>%{y:,.0f} crashes<extra></extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["hour"], y=df["ci_high"], mode="lines", line=dict(width=0),
                             hoverinfo="skip", showlegend=False), secondary_y=True)
    fig.add_trace(go.Scatter(x=df["hour"], y=df["ci_low"], mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor="rgba(239,71,111,0.18)",
                             hoverinfo="skip", showlegend=False), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=df["hour"], y=df["injury_rate"], mode="lines+markers", name="Injury rate % (right axis)",
        line=dict(color=C["danger"], width=3), marker=dict(size=7),
        customdata=np.column_stack([df["injury_crashes"], df["inj_known"], df["ci_low"], df["ci_high"]]),
        hovertemplate=("Hour %{x}:00<br>Injury rate %{y:.2f}%<br>95%% CI %{customdata[2]:.2f}–%{customdata[3]:.2f}%"
                       "<extra></extra>")), secondary_y=True)
    fig.update_xaxes(dtick=1, title="Hour of day (0 = midnight)")
    fig.update_yaxes(title_text="Crashes", rangemode="tozero", secondary_y=False)
    fig.update_yaxes(title_text="Crashes with ≥1 injury (%)", rangemode="tozero",
                     showgrid=False, secondary_y=True)
    return style(fig, height, "Crash volume and injury rate by hour of day", legend=True)


def heatmap_fig(df: pd.DataFrame, metric: str = "Crash count", min_n: int = 30,
                height: int = 380) -> go.Figure:
    if df["crashes"].sum() == 0:
        return empty_fig(height=height)
    if metric == "Crash count":
        z = df["crashes"].to_numpy(dtype=float).reshape(7, 24)
        text = np.vectorize(lambda v: f"{v:,.0f} crashes")(z)
        cbar = "Crashes"
        extra = ""
    else:
        z = df["injury_rate"].to_numpy(dtype=float).copy()
        z[df["inj_known"].to_numpy() < min_n] = np.nan            # too few crashes to trust
        z = z.reshape(7, 24)
        n = df["inj_known"].to_numpy().reshape(7, 24)
        text = np.vectorize(lambda v: "n/a" if np.isnan(v) else f"{v:.1f}% of crashes had injuries")(z)
        cbar = "Injury rate %"
        extra = f" (cells with < {min_n} crashes hidden)"
    fig = go.Figure(go.Heatmap(
        z=z, x=list(range(24)), y=DAY_NAMES, colorscale="YlOrRd", text=text,
        hovertemplate="%{y}, %{x}:00<br>%{text}<extra></extra>", colorbar=dict(title=cbar),
        xgap=1, ygap=1))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(dtick=1, title="Hour of day")
    return style(fig, height, f"{metric} by day of week and hour{extra}")


# ---------------------------------------------------------------- Section C: Factors
def top_factors_fig(df: pd.DataFrame, selected: Sequence[str] = (), top: int = 12,
                    scope_label: str = "vehicle 1", height: int = 460) -> go.Figure:
    d = df[df["crashes"] > 0].sort_values("crashes", ascending=False).head(top)
    if d.empty:
        return empty_fig(height=height)
    d = d.iloc[::-1]
    colors = _colors(list(d["factor"]), selected, C["primary"])
    fig = go.Figure(go.Bar(
        y=[short(f) for f in d["factor"]], x=d["crashes"], orientation="h", marker_color=colors,
        customdata=d["factor"], text=[f"{v:,.0f}" for v in d["crashes"]], textposition="outside",
        cliponaxis=False, hovertemplate="<b>%{customdata}</b><br>%{x:,.0f} crashes<extra></extra>"))
    fig.update_xaxes(title="Crashes", rangemode="tozero")
    return style(fig, height, f"Most frequently reported contributing factors ({scope_label}, excl. Unspecified)")


def factor_rate_fig(df: pd.DataFrame, overall_rate: float, selected: Sequence[str] = (),
                    min_crashes: int = 500, top: int = 12, height: int = 460) -> go.Figure:
    d = df[df["inj_known"] >= min_crashes].sort_values("injury_rate", ascending=False).head(top)
    if d.empty:
        return empty_fig(f"No factor has ≥ {min_crashes:,} crashes in this selection", height)
    d = d.iloc[::-1]
    colors = _colors(list(d["factor"]), selected, C["danger"])
    fig = go.Figure(go.Bar(
        y=[short(f) for f in d["factor"]], x=d["injury_rate"], orientation="h", marker_color=colors,
        error_x=dict(type="data", symmetric=False,
                     array=(d["ci_high"] - d["injury_rate"]).to_numpy(),
                     arrayminus=(d["injury_rate"] - d["ci_low"]).to_numpy(),
                     color=C["subtle"], thickness=1.2, width=3),
        customdata=np.column_stack([d["factor"], d["crashes"], d["ci_low"], d["ci_high"]]),
        text=[f"{v:.1f}%" for v in d["injury_rate"]], textposition="outside", cliponaxis=False,
        hovertemplate=("<b>%{customdata[0]}</b><br>Injury rate %{x:.2f}%<br>95%% CI "
                       "%{customdata[2]:.1f}–%{customdata[3]:.1f}%<br>%{customdata[1]:,.0f} crashes<extra></extra>")))
    if np.isfinite(overall_rate):
        fig.add_vline(x=overall_rate, line_dash="dash", line_color=C["subtle"],
                      annotation_text=f"All crashes {overall_rate:.1f}%", annotation_position="top")
    fig.update_xaxes(title="Crashes with ≥1 injury (%)", rangemode="tozero")
    return style(fig, height, f"Factors with the highest injury rates (≥ {min_crashes:,} crashes)")


def factor_scatter_fig(df: pd.DataFrame, overall_rate: float, selected: Sequence[str] = (),
                       min_crashes: int = 500, height: int = 520) -> go.Figure:
    d = df[df["inj_known"] >= min_crashes].copy()
    if d.empty:
        return empty_fig(f"No factor has ≥ {min_crashes:,} crashes in this selection", height)
    is_sel = d["factor"].isin(selected) if len(selected) else pd.Series(False, index=d.index)
    label_idx = set(d.nlargest(8, "crashes").index) | set(d.nlargest(4, "injury_rate").index) | set(d[is_sel].index)
    d["label"] = [short(f, 28) if i in label_idx else "" for i, f in zip(d.index, d["factor"])]
    colors = [C["accent"] if s else C["primary"] for s in is_sel]
    fig = go.Figure(go.Scatter(
        x=d["crashes"], y=d["injury_rate"], mode="markers+text", text=d["label"],
        textposition="top center", textfont=dict(size=10, color=C["subtle"]),
        marker=dict(size=13, color=colors, line=dict(width=1, color="#0B1220")),
        customdata=np.column_stack([d["factor"], d["ci_low"], d["ci_high"]]),
        hovertemplate=("<b>%{customdata[0]}</b><br>%{x:,.0f} crashes<br>Injury rate %{y:.2f}% "
                       "(95%% CI %{customdata[1]:.1f}–%{customdata[2]:.1f}%)<extra></extra>")))
    if np.isfinite(overall_rate):
        fig.add_hline(y=overall_rate, line_dash="dash", line_color=C["subtle"],
                      annotation_text=f"All crashes {overall_rate:.1f}%", annotation_position="bottom right")
    fig.update_xaxes(title="Number of crashes (log scale)", type="log")
    fig.update_yaxes(title="Crashes with ≥1 injury (%)", rangemode="tozero")
    return style(fig, height, "Frequency vs injury rate, by contributing factor")


# ---------------------------------------------------------------- Section D: Who
def road_user_fig(df: pd.DataFrame, height: int = 560) -> go.Figure:
    if df["crashes"].sum() == 0:
        return empty_fig(height=height)
    series = [("ped_inj", "Pedestrians", C["accent"]), ("cyc_inj", "Cyclists", C["good"]),
              ("mot_inj", "Motorists", C["primary"])]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=[s[1] + " injured" for s in series])
    comp, part = df[~df["partial"]], df[df["partial"]]
    for r, (col, name, color) in enumerate(series, start=1):
        fig.add_trace(go.Scatter(
            x=comp["year"], y=comp[col], mode="lines+markers", name=name,
            line=dict(color=color, width=3), marker=dict(size=7), showlegend=False,
            hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{y:,.0f}} injured<extra></extra>"), row=r, col=1)
        if len(part):
            fig.add_trace(go.Scatter(
                x=part["year"], y=part[col], mode="markers", showlegend=False,
                marker=dict(size=10, symbol="diamond-open", color=color, line=dict(width=2)),
                hovertemplate=f"<b>%{{x}} (partial year)</b><br>{name}: %{{y:,.0f}} injured<extra></extra>"),
                row=r, col=1)
        fig.update_yaxes(rangemode="tozero", row=r, col=1)
    fig.update_xaxes(dtick=1, title="Year", row=3, col=1)
    fig.update_annotations(font=dict(size=13, color=C["subtle"]), xanchor="left", x=0)
    return style(fig, height, "People injured per year, by road-user type (open diamonds = partial year)")


def vehicle_rate_fig(df: pd.DataFrame, overall_rate: float, selected: Sequence[str] = (),
                     min_crashes: int = 500, height: int = 420) -> go.Figure:
    d = df[df["inj_known"] >= min_crashes].sort_values("injury_rate")
    if d.empty:
        return empty_fig(f"No vehicle group has ≥ {min_crashes:,} crashes in this selection", height)
    colors = _colors(list(d["vehicle_group"]), selected, C["danger"])
    fig = go.Figure(go.Bar(
        y=d["vehicle_group"], x=d["injury_rate"], orientation="h", marker_color=colors,
        error_x=dict(type="data", symmetric=False,
                     array=(d["ci_high"] - d["injury_rate"]).to_numpy(),
                     arrayminus=(d["injury_rate"] - d["ci_low"]).to_numpy(),
                     color=C["subtle"], thickness=1.2, width=3),
        customdata=np.column_stack([d["crashes"], d["ci_low"], d["ci_high"]]),
        text=[f"{v:.1f}%" for v in d["injury_rate"]], textposition="outside", cliponaxis=False,
        hovertemplate=("<b>%{y}</b><br>Injury rate %{x:.2f}% (95%% CI %{customdata[1]:.1f}–%{customdata[2]:.1f}%)"
                       "<br>%{customdata[0]:,.0f} crashes involving this type<extra></extra>")))
    if np.isfinite(overall_rate):
        fig.add_vline(x=overall_rate, line_dash="dash", line_color=C["subtle"],
                      annotation_text=f"All crashes {overall_rate:.1f}%", annotation_position="top")
    fig.update_xaxes(title="Crashes with ≥1 injury (%)", rangemode="tozero")
    return style(fig, height, "Injury rate of crashes involving each vehicle type")


# ---------------------------------------------------------------- Compare
def compare_hour_fig(a: pd.DataFrame, b: pd.DataFrame, name_a: str, name_b: str,
                     height: int = 380) -> go.Figure:
    fig = go.Figure()
    for df, name, color in ((a, name_a, C["accent"]), (b, name_b, C["primary"])):
        tot = df["crashes"].sum()
        share = 100 * df["crashes"] / tot if tot else df["crashes"] * np.nan
        fig.add_trace(go.Scatter(x=df["hour"], y=share, mode="lines+markers", name=name,
                                 line=dict(color=color, width=3),
                                 hovertemplate=f"<b>{name}</b><br>%{{x}}:00 — %{{y:.2f}}% of its crashes<extra></extra>"))
    fig.update_xaxes(dtick=1, title="Hour of day")
    fig.update_yaxes(title="% of the area's crashes", rangemode="tozero")
    return style(fig, height, "When do crashes happen? (share of each area's own crashes)", legend=True)


def compare_factor_fig(a: pd.DataFrame, b: pd.DataFrame, name_a: str, name_b: str,
                       top: int = 8, height: int = 420) -> go.Figure:
    a = a.set_index("factor"); b = b.set_index("factor")
    sa, sb = a["crashes"].sum(), b["crashes"].sum()
    if sa == 0 and sb == 0:
        return empty_fig(height=height)
    shares = pd.DataFrame({
        name_a: 100 * a["crashes"] / sa if sa else np.nan,
        name_b: 100 * b["crashes"] / sb if sb else np.nan,
    })
    shares["tot"] = a["crashes"] + b["crashes"]
    shares = shares.sort_values("tot", ascending=False).head(top).iloc[::-1]
    fig = go.Figure()
    for name, color in ((name_a, C["accent"]), (name_b, C["primary"])):
        fig.add_trace(go.Bar(y=[short(i, 34) for i in shares.index], x=shares[name], name=name,
                             orientation="h", marker_color=color,
                             hovertemplate=f"<b>{name}</b><br>%{{x:.1f}}% of crashes with a factor<extra></extra>"))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="% of the area's crashes that have a recorded factor", rangemode="tozero")
    return style(fig, height, "Top contributing factors, side by side", legend=True)
