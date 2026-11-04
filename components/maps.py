"""PyDeck map builders.

The map never plots individual crashes. It draws aggregated square grid cells
(100 m - 1 km) computed by utils.data_helpers.grid_aggregate, so the browser
only receives a few thousand cells even though the dataset has 2M+ rows.

Every layer has an explicit `id` (required by st.pydeck_chart click selection).
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd
import plotly.colors as pc
import pydeck as pdk

from utils.schema import BOROUGH_VIEW, CITY_VIEW

# ---------------------------------------------------------------- colours
@lru_cache(maxsize=8)
def _lut(name: str, reverse: bool = False) -> np.ndarray:
    pts = [i / 255 for i in range(256)]
    cols = pc.sample_colorscale(name, pts)
    arr = np.array([[int(v) for v in re.findall(r"\d+", c)[:3]] for c in cols], dtype=np.uint8)
    return arr[::-1] if reverse else arr


def _to_rgba(t: np.ndarray, name: str, alpha: int = 210, reverse: bool = False) -> list:
    t = np.clip(np.nan_to_num(t, nan=0.0), 0, 1)
    rgb = _lut(name, reverse)[(t * 255).astype(int)]
    rgba = np.column_stack([rgb, np.full(len(rgb), alpha, dtype=np.uint8)])
    return rgba.astype(int).tolist()


def colorize(grid: pd.DataFrame, metric: str):
    """Return (rgba list, t in 0..1, legend dict) for a grid DataFrame.

    metric: 'crashes' | 'injury_rate' | 'fatal_crashes' | 'ratio'
    Scales are chosen so a few extreme cells don't wash out the map, and the
    legend states the scale honestly.
    """
    if metric == "ratio":
        v = np.log2(np.clip(grid["ratio"].to_numpy(dtype=float), 0.25, 4.0))
        t = (v + 2) / 4
        return (_to_rgba(t, "RdBu", reverse=True), t,
                dict(low="0.25× (under-represented)", high="4× (over-represented)",
                     mid="1× = same as all crashes", cmap="RdBu", reverse=True,
                     note="log scale, clipped to 0.25×–4×"))
    if metric == "injury_rate":
        v = grid["injury_rate"].to_numpy(dtype=float)
        lo, hi = np.nanpercentile(v, 5), np.nanpercentile(v, 95)
        hi = hi if hi > lo else lo + 1
        t = (v - lo) / (hi - lo)
        return (_to_rgba(t, "YlOrRd"), t,
                dict(low=f"{lo:.0f}%", high=f"{hi:.0f}%+", cmap="YlOrRd", reverse=False,
                     note="injury rate, linear between the 5th and 95th percentile of shown cells"))
    v = grid[metric].to_numpy(dtype=float)
    hi = max(np.nanpercentile(v, 99), 2.0)
    t = np.log1p(v) / np.log1p(hi)
    unit = "fatal crashes" if metric == "fatal_crashes" else "crashes"
    return (_to_rgba(t, "YlOrRd"), t,
            dict(low=f"1 {unit[:-1] if v.max() >= 1 else unit}", high=f"{hi:,.0f}+ {unit}",
                 cmap="YlOrRd", reverse=False, note="log scale per cell"))


def legend_html(leg: dict) -> str:
    cols = _lut(leg["cmap"], leg.get("reverse", False))
    stops = ", ".join(f"rgb({r},{g},{b})" for r, g, b in cols[::32])
    mid = f"<span style='opacity:.8'> · {leg['mid']}</span>" if leg.get("mid") else ""
    return (
        "<div style='font-size:12px;color:#9FB0C8;margin-top:4px'>"
        f"<div style='display:flex;align-items:center;gap:8px'><span>{leg['low']}</span>"
        f"<div style='flex:1;height:10px;border-radius:5px;background:linear-gradient(90deg,{stops})'></div>"
        f"<span>{leg['high']}</span></div>"
        f"<div style='margin-top:2px'>{leg['note']}{mid}</div></div>")


# ---------------------------------------------------------------- view state
def view_state(boroughs: Sequence[str] = (), extruded: bool = False,
               cell: Optional[tuple] = None) -> pdk.ViewState:
    """Camera: a selected hotspot wins, then a single borough, then the whole city."""
    if cell:
        from utils.data_helpers import cell_center
        size, ix, iy = cell
        lat, lon = cell_center(ix, iy, size)
        lat, lon, zoom = float(lat), float(lon), 14.5
    elif len(boroughs) == 1 and boroughs[0] in BOROUGH_VIEW:
        lat, lon, zoom = BOROUGH_VIEW[boroughs[0]]
    else:
        lat, lon, zoom = CITY_VIEW
    return pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom,
                         pitch=50 if extruded else 0, bearing=0)


# ---------------------------------------------------------------- layers
def cell_layer(grid: pd.DataFrame, metric: str, size_m: int, extruded: bool = False,
               pickable: bool = True, layer_id: str = "cells"):
    """Return (layer, legend). `grid` needs ix, iy, lat, lon, crashes, ..."""
    if grid.empty:
        return None, None
    rgba, t, legend = colorize(grid, metric)
    df = pd.DataFrame({
        "lon": grid["lon"].astype(float), "lat": grid["lat"].astype(float),
        "ix": grid["ix"].astype(int), "iy": grid["iy"].astype(int), "size": int(size_m),
        "crashes": grid["crashes"].astype(int),
        "injury_txt": np.where(grid["inj_known"] > 0,
                               grid["injury_rate"].round(1).astype(str) + "%", "n/a")
        if "inj_known" in grid else "n/a",
        "color": rgba,
        "elev": (np.clip(t, 0, 1) * 1800.0) if extruded else 0.0,
    })
    if "fatal_crashes" in grid:
        df["fatal"] = grid["fatal_crashes"].astype(int)
    else:
        df["fatal"] = 0
    if "subset_crashes" in grid:
        df["subset"] = grid["subset_crashes"].astype(int)
        df["ratio_txt"] = grid["ratio"].round(2).astype(str) + "×"
    layer = pdk.Layer(
        "GridCellLayer", id=layer_id, data=df, get_position="[lon, lat]",
        get_fill_color="color", get_elevation="elev", cell_size=int(size_m),
        extruded=bool(extruded), elevation_scale=1, coverage=0.94, opacity=0.9,
        pickable=pickable, auto_highlight=True)
    return layer, legend


def selected_cell_layer(cell: Optional[tuple]):
    if not cell:
        return None
    from utils.data_helpers import cell_center
    size, ix, iy = cell
    lat, lon = cell_center(ix, iy, size)
    return pdk.Layer(
        "ScatterplotLayer", id="selected_cell",
        data=pd.DataFrame({"lon": [float(lon)], "lat": [float(lat)]}),
        get_position="[lon, lat]", get_radius=float(size) * 0.75, radius_units="meters",
        radius_min_pixels=16, stroked=True, filled=False, get_line_color=[245, 184, 65, 255],
        line_width_min_pixels=3, pickable=False)


@lru_cache(maxsize=2)
def load_boroughs(path: str) -> Optional[dict]:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def borough_layers(geojson: dict, selected: Sequence[str], pickable: bool,
                   stats: Optional[dict] = None):
    """Return [fill layer (clickable), outline layer].

    `stats` = {BOROUGH: (crashes, injury_rate_pct)} from the borough table; it is
    copied onto each feature (top-level, so deck.gl tooltips can read it).
    Selected boroughs get a tint and a gold outline.
    """
    gj = copy.deepcopy(geojson)
    for feat in gj["features"]:
        name = str(feat["properties"].get("borough", "")).upper()
        on = (not selected) or name in selected
        feat["properties"]["fill"] = [78, 168, 222, 46 if (selected and on) else 14]
        feat["properties"]["line"] = [245, 184, 65, 255] if (selected and on) else [159, 176, 200, 170]
        feat["label"] = name.title()
        n, rate = (stats or {}).get(name, (None, None))
        feat["n_txt"] = f"{int(n):,}" if n is not None else "–"
        feat["rate_txt"] = f"{rate:.1f}%" if rate is not None and rate == rate else "–"
    fill = pdk.Layer("GeoJsonLayer", id="boroughs", data=gj, stroked=False, filled=True,
                     get_fill_color="properties.fill", pickable=pickable, auto_highlight=pickable)
    line = pdk.Layer("GeoJsonLayer", id="borough_outline", data=gj, stroked=True, filled=False,
                     get_line_color="properties.line", line_width_min_pixels=2, pickable=False)
    return fill, line


_TIP_STYLE = {"backgroundColor": "#131C2E", "color": "#E6EDF7", "fontSize": "12px",
              "border": "1px solid #43536D", "borderRadius": "8px", "padding": "8px 10px"}

CELL_TOOLTIP = {
    "html": ("<div style='font-weight:700;margin-bottom:2px'>{crashes} crashes</div>"
             "Injury rate: <b>{injury_txt}</b><br/>Fatal crashes: <b>{fatal}</b>"
             "<div style='opacity:.65;margin-top:4px'>Click to select this area</div>"),
    "style": _TIP_STYLE,
}
BOROUGH_TOOLTIP = {
    "html": ("<div style='font-weight:700;margin-bottom:2px'>{label}</div>"
             "{n_txt} crashes · injury rate <b>{rate_txt}</b>"
             "<div style='opacity:.65;margin-top:4px'>Click to select this borough</div>"),
    "style": _TIP_STYLE,
}
RATIO_TOOLTIP = {
    "html": ("<div style='font-weight:700;margin-bottom:2px'>{ratio_txt} vs. all crashes</div>"
             "{subset} factor crashes of {crashes} in this cell"),
    "style": _TIP_STYLE,
}


def make_deck(layers: list, vs: pdk.ViewState, tooltip: Optional[dict] = None) -> pdk.Deck:
    # map_style=None follows the Streamlit theme (documented by Streamlit); the app theme is dark.
    return pdk.Deck(layers=[l for l in layers if l is not None], initial_view_state=vs,
                    map_style=None, tooltip=tooltip or CELL_TOOLTIP)


def decode_pick(objects: dict) -> Optional[dict]:
    """Turn st.pydeck_chart selection objects into {'cell': (...)} or {'borough': 'X'}."""
    if not objects:
        return None
    cells = objects.get("cells") or []
    if cells:
        o = cells[0]
        try:
            return {"cell": (int(o["size"]), int(o["ix"]), int(o["iy"]))}
        except (KeyError, TypeError, ValueError):
            return None
    boros = objects.get("boroughs") or []
    if boros:
        o = boros[0]
        props = o.get("properties", o) if isinstance(o, dict) else {}
        name = str(props.get("borough", "")).upper()
        return {"borough": name} if name else None
    return None
