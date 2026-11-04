"""Smoke test of the UI code paths using STAND-IN modules for streamlit,
plotly and pydeck (not installable in the dev sandbox).

Proves   : every section, presentation step, sidebar, map and app.py itself run
           end-to-end on SYNTHETIC data under many filter combinations without
           Python errors (bad column names, shape bugs, NameErrors, state bugs).
Does NOT prove: that the real Streamlit/Plotly/PyDeck APIs accept the calls or
           that anything renders correctly. Run the real app for that.
"""
import json
import runpy
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class StopApp(Exception):
    pass


class Ctx:
    def __init__(self, st): self._st = st
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name): return getattr(self._st, name)


class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.calls = []
        self.column_config = MagicMock()
        self.sidebar = Ctx(self)
        self.next_pick = {}

    def cache_data(self, *a, **k):
        if a and callable(a[0]): return a[0]
        return lambda fn: fn
    cache_resource = cache_data

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [Ctx(self) for _ in range(n)]
    def expander(self, *a, **k): return Ctx(self)
    def container(self, *a, **k): return Ctx(self)
    def popover(self, *a, **k): return Ctx(self)
    def empty(self): return Ctx(self)

    def _get(self, key, default): return self.session_state.get(key, default) if key else default
    def radio(self, label, options, key=None, index=0, **k): return self._get(key, list(options)[index])
    def segmented_control(self, label, options, key=None, default=None, **k): return self._get(key, default)
    def select_slider(self, label, options=(), value=None, key=None, **k): return self._get(key, value if value is not None else list(options)[0])
    def multiselect(self, label, options, default=None, key=None, **k): return self._get(key, list(default or []))
    def slider(self, label, lo=0, hi=1, value=None, step=None, key=None, **k): return self._get(key, value if value is not None else lo)
    def selectbox(self, label, options, index=0, key=None, **k): return self._get(key, list(options)[index])
    def toggle(self, *a, key=None, **k): return self._get(key, False)
    def checkbox(self, *a, key=None, **k): return self._get(key, False)
    def button(self, *a, **k): return False

    def pydeck_chart(self, deck, **k):
        self.calls.append("pydeck")
        return types.SimpleNamespace(selection={"objects": self.next_pick})

    def stop(self): raise StopApp()
    def rerun(self): raise StopApp()

    def __getattr__(self, name):
        def f(*a, **k):
            self.calls.append(name)
        return f


fake_st = FakeSt()
sys.modules["streamlit"] = fake_st

plotly = types.ModuleType("plotly")
go, sub = MagicMock(name="go"), MagicMock(name="subplots")
colors = types.ModuleType("plotly.colors")
colors.sample_colorscale = lambda name, pts: ["rgb(200, 100, 50)"] * len(pts)
plotly.graph_objects, plotly.subplots, plotly.colors = go, sub, colors
sys.modules.update({"plotly": plotly, "plotly.graph_objects": go, "plotly.subplots": sub,
                    "plotly.colors": colors, "pydeck": MagicMock(name="pydeck")})

from dataclasses import replace                                         # noqa: E402

from tests.make_synthetic_data import make_raw                          # noqa: E402
from utils.prepare import transform_raw                                  # noqa: E402
from utils import data_helpers as dh, cached                             # noqa: E402
from components import filters as filters_ui, sections, maps, ui, present   # noqa: E402

PROC, META = transform_raw(make_raw(30000))
D = dh.CrashData(PROC, META)
ss = fake_st.session_state
SECTION_NAMES = ("overview", "where", "when", "factors", "who", "compare", "methods")


def numbers(f):
    fk = f.to_json()
    return cached.kpis(D, fk), cached.baseline_kpis(D, fk)


def run_explore(f):
    k, kb = numbers(f)
    ui.kpi_cards(k, kb, f.severity, dh.is_filtered(f))
    ui.filter_chips(f, "Years")
    if k["crashes"] == 0:
        return
    for name in SECTION_NAMES:
        getattr(sections, name)(D, f, k, kb)


def run_present(f):
    k, kb = numbers(f)
    if k["crashes"] == 0:
        return
    for step in range(len(present.STEPS)):
        ss["pstep"] = step
        present.render(D, f, k, kb)


def main():
    filters_ui.init_state(D)
    f0, _ = filters_ui.render_sidebar(D)
    assert isinstance(f0, dh.Filters)
    g = dh.grid_aggregate(D, dh.build_mask(D, f0), 250).sort_values("crashes", ascending=False).iloc[0]
    combos = {
        "default": f0, "all years": replace(f0, year_range=(2012, 2025)),
        "brooklyn": replace(f0, boroughs=("BROOKLYN",)),
        "two boroughs": replace(f0, boroughs=("QUEENS", "BRONX")),
        "factor v1": replace(f0, factors=("Unsafe Speed",)),
        "factor any": replace(f0, factors=("Unsafe Speed", "Following Too Closely"), factor_scope="any"),
        "vehicle": replace(f0, vehicles=("Bicycle / E-bike / E-scooter",)),
        "injury only": replace(f0, severity="injury"), "fatal only": replace(f0, severity="fatal"),
        "days+hours": replace(f0, days=(0, 6), hour_range=(7, 9)),
        "cell": replace(f0, cell=(250, int(g["ix"]), int(g["iy"]))),
        "empty": replace(f0, year_range=(2012, 2012), boroughs=("STATEN ISLAND",), severity="fatal", hour_range=(3, 3)),
    }
    for name, f in combos.items():
        run_explore(f); run_present(f)
        print("ok  ", name)

    # map variants (with and without borough polygons)
    rects = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"borough": b}, "geometry": {"type": "Polygon", "coordinates": [[
            [-74 + i * .1, 40.5], [-73.95 + i * .1, 40.5], [-73.95 + i * .1, 40.6], [-74 + i * .1, 40.6], [-74 + i * .1, 40.5]]]}}
        for i, b in enumerate(["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"])]}
    tmp = Path(tempfile.mkdtemp()) / "b.geojson"
    tmp.write_text(json.dumps(rects))
    for label, path in (("no polygons", ROOT / "data/processed/_missing.geojson"), ("polygons", tmp)):
        sections.BOUNDARY_PATH = path
        maps.load_boroughs.cache_clear()
        for metric in ("Crashes", "Injury rate", "Fatal crashes"):
            for ext in (False, True):
                ss["map_metric"], ss["map_3d"] = metric, ext
                for mode in ("Borough", "Hotspot cell"):
                    ss["click_mode"] = mode
                    k, kb = numbers(f0)
                    sections.overview(D, f0, k, kb)
                    sections.overview(D, replace(f0, boroughs=("BROOKLYN",)), *numbers(replace(f0, boroughs=("BROOKLYN",))))
        print("ok   map variants:", label)
    ss.update(map_metric="Crashes", map_3d=False, click_mode="Hotspot cell")

    for view in ("Where they occur", "Over/under-represented"):
        ss["cmp_view"] = view
        sections.compare(D, f0, *numbers(f0))
    ss["cmp_mode"] = "Borough vs borough"
    sections.compare(D, f0, *numbers(f0))
    ss.pop("cmp_mode"); ss.pop("cmp_view")
    print("ok   compare views")

    # click handling
    sections.BOUNDARY_PATH = ROOT / "data/processed/_missing.geojson"; maps.load_boroughs.cache_clear()
    ss["click_mode"] = "Hotspot cell"
    fake_st.next_pick = {"cells": [{"size": 250, "ix": 5, "iy": 7}]}
    ss["last_pick"] = None
    try:
        sections.overview(D, f0, *numbers(f0)); raise AssertionError("expected st.rerun on a new pick")
    except StopApp:
        assert ss["pending"] == {"cell": (250, 5, 7)}
    filters_ui.apply_pending()
    assert ss["sel_cell"] == (250, 5, 7)
    f1, _ = filters_ui.render_sidebar(D)
    assert f1.cell == (250, 5, 7)
    assert maps.decode_pick({"boroughs": [{"properties": {"borough": "Queens"}}]}) == {"borough": "QUEENS"}
    ss["pending"] = {"borough": "QUEENS"}; filters_ui.apply_pending()
    assert ss["f_boroughs"] == ["QUEENS"] and ss["sel_cell"] is None
    fake_st.next_pick = {}
    print("ok   click -> pending -> filter round trip")

    # quick selectors drive the same state as the sidebar
    ss["f_boroughs"] = []
    filters_ui.borough_quick(); assert ss["quick_boro"] == "All NYC"
    ss["quick_boro"] = "Staten Island"; filters_ui._on_quick_borough()
    assert ss["f_boroughs"] == ["STATEN ISLAND"] and ss["sel_cell"] is None
    ss["f_boroughs"] = ["QUEENS", "BRONX"]; filters_ui.borough_quick(); assert ss["quick_boro"] is None
    ss["quick_factor"] = "Unsafe Speed"; filters_ui._on_quick_factor(); assert ss["f_factors"] == ["Unsafe Speed"]
    ss["quick_factor"] = "All factors"; filters_ui._on_quick_factor(); assert ss["f_factors"] == []
    ss["pstep"] = 3; present._go(delta=1); assert ss["pstep"] == 4 and ss["pstep_sel"] == present.NAMES[4]
    present._go(delta=99); assert ss["pstep"] == len(present.STEPS) - 1
    ss["pstep_sel"] = "Where"; present._on_select(); assert ss["pstep"] == 1
    print("ok   quick selectors + presentation navigation")

    # the real app.py entry script, both modes, every section
    cached.data_available = lambda: True
    cached.load_data = lambda: D
    for k_ in list(ss):
        ss.pop(k_)
    for mode in ("Explore", "Present"):
        ss["mode"] = mode
        for sec in (sections_ for sections_ in ("Overview", "Where", "When", "Factors", "Who", "Compare", "Data & Methods")):
            ss["section"] = sec
            ss["pstep"] = ["Overview", "Where", "When", "Factors", "Who", "Compare"].index(sec) if sec != "Data & Methods" else 5
            runpy.run_path(str(ROOT / "app.py"))
        print("ok   app.py", mode)
    print("\nSMOKE TEST PASSED (stand-in libraries; see module docstring for what this does not prove)")


if __name__ == "__main__":
    main()
