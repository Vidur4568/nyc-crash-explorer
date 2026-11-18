# NYC Crash Explorer

**Busiest is not the same as most dangerous.** An interactive dashboard for analyzing 2.18M+ New York City motor vehicle collisions, built with Streamlit, Pandas, Plotly, and PyDeck.

**[Live demo](https://nyc-crash-explorer.streamlit.app/)**

**Research question:** Where, when, and under what circumstances are motor vehicle collisions most dangerous in NYC?

The core idea running through the app is that the places, times, and factors with the most crashes are not necessarily the ones where crashes are most likely to injure someone. Every view separates crash **counts** from injury **rates** to make that difference visible.

## Key findings

Complete years 2013 to 2024 unless noted. The NYC-wide injury rate (share of crashes with at least one injured person) is 23.7%.

**Place.** Manhattan has the 3rd most crashes (335k) but the lowest injury rate (18.5%). The Bronx has the 4th most crashes (223k) but the 2nd-highest injury rate (24.8%). Brooklyn has the most recorded crashes and the highest injury rate (25.6%).

**Factor.** Driver inattention is the most commonly recorded factor (422,374 crashes), and 25.9% of those crashes involve an injury. Failure to yield is the second most common (124,160 crashes) and 41.6% involve an injury. Among factors with at least 500 crashes, the highest injury rates are pedestrian/bicyclist error (75.6%), traffic control disregarded (46.9%), passenger distraction (46.1%), and unsafe speed (42.3%).

**Hour.** 4 PM is the busiest hour (155,929 crashes, 22.7% injury rate), but 9 PM has the highest injury rate (28.8%, on 79,214 crashes). This hourly view covers all recorded crashes from July 2012 to May 2025.

**Year.** Recorded crashes fell 57% from 2019 (211,486) to 2024 (91,297), including a 47% drop from 2019 to 2020. Injuries fell much less: motorists injured fell 18% and pedestrians 9%, while cyclists injured rose 3%. In 2020, crashes fell 47% yet cyclist injuries rose 12% (4,986 to 5,576). Pedestrian, cyclist, and motorist injuries per 100 recorded crashes rose from 29 to 57.

These are associations in police-reported data, not causes, and with no traffic or population data they are not measures of personal risk.

## What it does

The app has seven sections that all share one set of filters (borough, years, contributing factor, vehicle type, severity, day of week, and hour):

| Section | What it shows |
|---|---|
| **Overview** | An interactive hotspot map colored by crash count, injury rate, or fatal crashes, with borough buttons, a spotlight panel for the selected area, and a top-10 hotspot table |
| **Where** | Crashes and injury rates by borough |
| **When** | Trends over time, volume vs. injury rate by hour, and a day-of-week by hour heatmap |
| **Factors** | Most common contributing factors, highest injury rates, and a frequency vs. severity scatter |
| **Who** | Pedestrian, cyclist, and motorist injury trends, plus injury rates by vehicle type |
| **Compare** | Side-by-side factor maps and borough comparisons |
| **Data & Methods** | Definitions, limitations, and a data-quality report |

Selecting a borough, factor, or map cell updates the KPI cards (crashes, people injured, people killed, injury rate, fatality rate), the map, and every chart together. KPI cards show how a selection differs from NYC overall for the same years. A **Present mode** turns the app into a guided six-step walkthrough with speaker notes.

Every chart includes a plain-language description, a takeaway computed from the currently filtered data rather than written by hand, and a note on how to read it and where it falls short.

## Data and method

- **Source:** NYC Motor Vehicle Collisions, Crashes (NYPD / NYC Open Data), 2,180,794 recorded crashes from July 2012 to May 2025. The default view uses complete years only (2013 to 2024, 2,046,637 crashes).
- **Partial years excluded.** 2012 (July to December) and 2025 (January to May) do not cover a full year, so they are left out of the default range and drawn as open markers.
- **Rates use recorded outcomes only.** Crashes with a missing injury or fatality value are not counted as "no injury."
- **Missing data shown openly.** About 31% of crashes have no borough and 33.6% have no specified factor, and 11% have no coordinates. Missing boroughs appear as "Unknown" instead of being dropped, and invalid coordinates are removed from the map only. An optional step fills them in from coordinates using borough boundary polygons.
- **Map scale.** Crashes are grouped into 250 m cells (10,780 cells hold about 1.8M crashes with valid locations), so the browser never loads individual crashes.
- **Uncertainty shown.** Rate charts display 95% confidence intervals, and late-night hours with few crashes are flagged as less certain.
- **Rate cards ignore the severity filter.** An injury rate calculated on injury-only crashes would trivially be 100%.

## Testing

The data pipeline, filters, aggregations, and insight sentences are tested against independent Pandas calculations on synthetic data (23 pipeline tests and 13 insight tests), and a smoke test runs every screen in both modes.

```bash
python tests/test_pipeline.py && python tests/test_insights.py && python tests/smoke_ui.py
```

## Run locally

Requires Python 3.10+ and Streamlit 1.50 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

1. Download `Motor_Vehicle_Collisions_-_Crashes_20250603.csv` from Kaggle and place it in `data/raw/`.
2. Build the processed dataset: `python scripts/prepare_data.py`
3. Optional, enables clicking boroughs on the map: `python scripts/download_boundaries.py`
4. Launch: `streamlit run app.py`

## Project structure

```text
app.py            entry point: header, mode switch, KPI strip, navigation
components/       UI theme, sidebar filters, map, charts, sections, present mode
utils/            data preparation, filters and aggregations, computed insights, caching
scripts/          data preparation and borough boundary scripts
tests/            pipeline, insight, and UI smoke tests
notebooks/        original exploratory analysis
docs/             notebook review and upgrade notes
```

## Limitations

- **No exposure data.** Without population, traffic volume, or mileage, counts and rates describe recorded crashes, not personal risk.
- **Contributing factors are recorded, not proven causes.** "Involves" does not mean "at fault."
- **Vehicle groups are keyword rules** applied to free-text vehicle types, so some grouping is approximate.
- **Reporting practices change over time** (for example around 2020). The app flags this but cannot correct it.
- **Desktop-oriented layout,** with no persistent URLs for filter state and no street-level labels for hotspots.

## Team

Built by a four-person Management Information Systems Association (MISA) project team at UT Austin: Vidur Bhardwaj (team lead), Terran Roberson, Shivani Sarangam, and Nithika Neela.

## Data sources

NYC Motor Vehicle Collisions, Crashes (NYPD / NYC Open Data), via Kaggle. NYC Department of City Planning, Borough Boundaries (Clipped to Shoreline).
