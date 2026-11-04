# 🚦 NYC Crash Explorer

Interactive analysis of New York City motor vehicle collisions — **Streamlit + Pandas + Plotly + PyDeck**.

**Research question:** *Where, when, and under what circumstances are motor vehicle collisions most dangerous in NYC?*

Two modes share one data layer and one set of filters:

| Mode | For | What it is |
|---|---|---|
| **Explore** | analysis | map-first Overview + tabs (Where · When · Factors · Who · Compare · Data & Methods), sidebar filters |
| **Present** | your final demo | a guided 6-step, ~5-minute story with live-demo buttons and speaker notes |

Every chart has a title, a one-line "what this measures", a "why it matters" line, a **data-driven takeaway** (computed from the
filtered numbers, never hand-written) and a "How to read this · limits" note.

> **Status honesty.** The data pipeline, filters, aggregations and insight sentences are unit-tested against independent pandas
> calculations (on *synthetic* data), and every screen's code path is smoke-tested with stand-in libraries. The v1 app has been run
> on the real dataset; the v2 upgrade (see `docs/UPGRADE_NOTES.md`) has **not** yet been run in a browser.

---

## 1. Setup (VS Code)

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate            # macOS/Linux      (Windows: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt      # re-run after upgrading: Streamlit >= 1.50 is required
```
In VS Code: `Cmd/Ctrl+Shift+P` ▸ **Python: Select Interpreter** ▸ the `.venv` one.

## 2. Prepare the data (once)

1. Put `Motor_Vehicle_Collisions_-_Crashes_20250603.csv` (Kaggle) in `data/raw/`.
2. `python scripts/prepare_data.py --sample 100000 --dry-run` — prints a data-quality report, writes nothing. Read the vehicle-type table.
3. `python scripts/prepare_data.py` — writes `data/processed/crashes.parquet` + `meta.json`.

### Borough polygons (enables clicking boroughs) — one command
```bash
python scripts/download_boundaries.py
```
Downloads NYC Department of City Planning "Borough Boundaries (Clipped to Shoreline)", converts it for the app and writes
`data/processed/nyc_boroughs.geojson`. If the download fails it prints the manual steps (download GeoJSON in EPSG:4326 from the
[DCP page](https://www.nyc.gov/site/planning/data-maps/open-data/districts-download-metadata.page), save as
`data/raw/nyc_boroughs_raw.geojson`, run `python scripts/prepare_boundaries.py`).

Optional: afterwards re-run `python scripts/prepare_data.py` to also **fill the ~31% of crashes with no borough from their
coordinates** (then tick the sidebar checkbox; off by default so numbers match the original notebook).

## 3. Run
```bash
streamlit run app.py        # http://localhost:8501
```

## 4. Using it

**Explore mode**
- **Overview** – the map is the centerpiece. One toolbar row: borough buttons (zoom + filter), colour by crashes / injury rate /
  fatal crashes, cell size, click mode, ⚙ (3D, min crashes per cell). Click a borough or hotspot cell: the map zooms, a gold ring marks
  the cell, and the KPI cards, spotlight panel and charts all follow.
- **KPI cards** show crashes, people injured/killed (people, not crashes), injury rate and fatality rate (% of crashes) — each with
  its unit, and with the **difference from NYC for the same years** whenever a filter is active.
- **Sidebar** is grouped *Where / When / What*. Charts for a dimension keep showing all its values with your selection highlighted
  (borough bars stay visible when Brooklyn is selected). Rate charts and the rate cards ignore the severity filter (an injury rate of
  injury-only crashes would be trivially 100%).

**Present mode** (toggle top-right) – sidebar hidden, bigger visuals, KPI strip stays on screen:
1. *The big picture* → 2. *Where* (borough buttons / click) → 3. *When* → 4. *Factors* (factor buttons: watch KPIs, charts and map change)
→ 5. *Who* → 6. *Takeaways & limits* (computed findings, data-aware limitations, next steps).
Use **Back / Next** or click a step name. **🗒 Speaker notes** gives three talking points per step with numbers from the current selection.
Filters you set in Explore mode carry over; the borough/factor buttons change the same filters.

## 5. Deploy (Streamlit Community Cloud)
1. Push to GitHub. `data/raw/` is git-ignored; **commit `data/processed/`** (parquet + `meta.json` + `nyc_boroughs.geojson`).
2. GitHub rejects files > 100 MB (warns at 50 MB). If `crashes.parquet` is too big: drop columns you don't need (e.g. `collision_id`),
   restrict years, use Git LFS (verify current Streamlit Cloud support), or host the file elsewhere and download it at startup.
3. <https://share.streamlit.io> ▸ Create app ▸ repo/branch ▸ main file `app.py` ▸ Deploy.
4. Community Cloud has limited memory (check current limits). Data loads once per server via a cached read.
5. Test the deployed link before presenting; keep `streamlit run app.py` working locally as a backup.

## 6. Project structure
```
app.py                      entry point: header, mode switch, KPI strip, navigation
components/
  ui.py                     CSS theme, KPI cards, chart cards (title + explainer + takeaway + limits)
  filters.py                grouped sidebar, borough/factor quick buttons, map-click handshake
  maps.py                   PyDeck: hotspot grid, borough polygons, tooltips, legends, zoom-to-selection
  charts.py                 Plotly figures (semantic colours: blue=counts, coral=rates, gold=selection)
  sections.py               Explore tabs + shared map toolbar/view
  present.py                guided presentation mode + speaker notes
utils/
  schema.py                 constants          prepare.py        raw CSV -> compact table (pure)
  data_helpers.py           filters, masks, aggregations, cache-key helpers (pure)
  insights.py               sentences computed from tables (pure)
  cached.py                 Streamlit cache wrappers (canonical keys)
scripts/
  prepare_data.py           CSV -> parquet + meta      download_boundaries.py / prepare_boundaries.py   borough GeoJSON
tests/
  make_synthetic_data.py    SYNTHETIC messy fixture (never real results)
  test_pipeline.py          23 tests vs pandas oracles   test_insights.py   13 tests (insight text + cache keys)
  smoke_ui.py               runs every screen, both modes and app.py with stand-in libraries
notebooks/  docs/           original notebook · notebook_review.md · UPGRADE_NOTES.md
```
Run tests (no Streamlit needed): `python tests/test_pipeline.py && python tests/test_insights.py && python tests/smoke_ui.py`

## 7. Five-minute demo (use Present mode)
| Step | ~Time | Do |
|---|---|---|
| 1 Big picture | 30 s | read the KPI cards, explain *crash vs injury rate*, note partial years excluded |
| 2 Where | 60 s | click **Brooklyn**; show map zoom + KPI deltas vs NYC; switch colour to *Injury rate* ("busy ≠ dangerous") |
| 3 When | 60 s | hour chart (volume vs severity differ) → heatmap → injury-rate view |
| 4 Factors | 70 s | click **Unsafe Speed**; watch KPI injury rate, ranking and map; state "recorded, not proven cause" |
| 5 Who | 40 s | road-user trends and vehicle rates; "involves ≠ at fault" |
| 6 Takeaways | 40 s | read two computed findings, the limits, the next steps |

## Known limitations & what still needs work
- **v2 UI not yet run in a browser** (see `docs/UPGRADE_NOTES.md` for the checklist). Expect small layout/API fixes on first run.
- **Borough download endpoint** (`download_boundaries.py`) could not be test-called by the author; the manual route is documented.
- **Map click selection** uses PyDeck picking via `st.pydeck_chart(on_select=…)`; v1 confirmed hotspot-cell clicks work. Borough-polygon clicks are new.
- **Vehicle groups** are keyword rules; review the audit table (`_VEHICLE_RULES` in `utils/prepare.py`).
- **No exposure data** (population, traffic volume): counts and rates describe recorded crashes, not personal risk.
- Reporting practices and events (e.g. 2020) change over time; the app flags but cannot correct this.
- Desktop-oriented layout; no persistent URLs for filter state; no street-level labels for hotspots.

## Data sources
NYC Motor Vehicle Collisions – Crashes (NYPD / NYC Open Data) via Kaggle · NYC Department of City Planning – Borough Boundaries (Clipped to Shoreline).
