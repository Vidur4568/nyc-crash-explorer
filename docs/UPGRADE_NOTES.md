# v2 upgrade notes

Built incrementally on the working v1: the **calculation layer (`prepare.py`, `data_helpers.py`) is unchanged** apart from additive
helpers, and all 23 original tests still pass. Everything below is new or changed.

## What changed

**Design & layout**
- New theme (consistent blue = counts, coral = rates, gold = selection), tighter spacing, hidden Deploy button, responsive KPI grid.
- Map-first Overview: borough buttons, colour/size/click mode in **one toolbar row**, map height 560, compact spotlight panel beside it.
- KPI cards rebuilt as HTML cards: each states its **unit** ("people, not crashes", "% of crashes with ≥1 injury") and shows the
  **difference from NYC (same years)** when a filter is active.
- Sidebar grouped *Where / When / What*; Reset is disabled when nothing is filtered.

**Map interactions**
- Borough buttons zoom + filter; clicking a borough polygon does the same (needs boundary file).
- A selected hotspot now **zooms the map to it** and shows a ring that stays visible at any zoom (v1 ring was ~1 px at city zoom).
- Hover tooltips: cells (crashes, injury rate, fatal crashes), boroughs (crashes, injury rate).
- `scripts/download_boundaries.py`: one-command borough polygons (+ `prepare_boundaries.py` accepts several property layouts).

**Explainability**
- Every chart is a "chart card": title, what it measures, why it matters, a **computed takeaway**, and a limits note (`utils/insights.py`).
  Statements read numbers from the same tables as the charts, mention CI overlap, and avoid causal wording; each returns nothing when data can't support it.
- Data-aware limitations (missing borough %, unspecified factors, missing coordinates, partial years).

**Presentation mode** (`components/present.py`)
- 6 steps, progress bar with suggested timing, Back/Next, live-demo borough and factor buttons, speaker notes with computed numbers,
  closing slide with computed findings + limits + next steps.

**Performance**
- Cache keys are *canonicalised*: filters a table ignores are reset before keying (`data_helpers.canonical_key`). Clicking a hotspot no
  longer recomputes the map grid or borough charts; changing borough does not recompute borough charts. Masks proven identical in tests.
- Measured (synthetic rows replicated to 2.19M, **uncached** worst case, fake UI): each tab/step built in ≤ ~1.3 s.

## Tested here (synthetic data / stand-in libraries)
- 23 pipeline tests + 13 new tests (insight sentences vs pandas oracles; canonical-key mask equality; baseline filters) – pass.
- Smoke test: every Explore section, all 6 Present steps, 12 filter combinations, borough polygons on/off, click→filter round trip,
  quick selectors, navigation, and the real `app.py` in both modes – pass.
- `normalize()` for borough GeoJSON with 3 property layouts + non-degree CRS rejection – pass.

## NOT tested – please check on first run (in this order)
1. `pip install -r requirements.txt` (Streamlit ≥ 1.50) and `streamlit run app.py` starts without errors.
2. **New Streamlit widgets**: segmented controls (mode, section, borough buttons, colour/size), popovers (⚙, ⓘ), `st.progress(text=…)`.
3. KPI cards render as styled cards; check text fits at your screen width.
4. Overview fits ~one screen at your resolution; map height (560) may need tuning (`sections.overview`).
5. Click a hotspot → map zooms, gold ring visible, KPI deltas appear. Click "Clear hotspot".
6. `python scripts/download_boundaries.py` → restart → click a borough on the map.
7. Present mode: all 6 steps, Back/Next, step buttons, sidebar hidden, factor buttons change KPIs/map, speaker notes.
8. Chart cards: takeaway text matches what the chart shows (spot-check 3 against the notebook).
9. Sanity check: All available years + no filters = 2,180,794 crashes.
10. Visual polish (fonts, spacing, dark theme contrast) — I could not see the rendered result.
