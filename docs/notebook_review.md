# Review of `Motor_Vehicle_Collisions.ipynb`

Based on the code cells and saved outputs of the notebook that was uploaded.
Only this notebook (and the project brief) were available. The Week 1–3 notebooks and the CSV were **not**,
so numbers below come from the notebook's own saved outputs, not from re-running anything.

## What the notebook already does (and where it lives in the app)

| Notebook work | Status | In the app |
|---|---|---|
| `head/shape/info/describe/columns`, injury filters, Brooklyn filter | exploration only | not repeated; superseded by the sidebar filters |
| Missing-data audit (`isna().sum()`, % missing) | done | `utils/prepare.py` data-quality report + "Data & Methods" tab |
| Date parsing, `ANY_INJURY`, `ANY_FATALITY`, `YEAR`, `MONTH`, `DAY_OF_WEEK`, `HOUR` | done | `utils/prepare.py` (same definitions, plus fixes below) |
| Collisions by borough, injuries by borough, collisions over time, top factors, day of week | done | Overview, Where, When, Factors |
| A. Injury rate by borough | done | Where / Overview (now with 95% CI) |
| B. Factor vs injury rate (min 1000 crashes) | done | Factors (min-crash slider, default 500; set to 1000 to match) |
| C. Injury rate by hour | done | When |
| D. Day × hour heatmap | done (counts) | When (counts **and** injury-rate version) |
| E. Ped/cyclist/motorist injuries over time | done | Who |
| F. Frequency vs severity scatter | done | Factors |
| G. Vehicle-type injury rates | **not in notebook** | Who (new) |
| H. Geographic density by factor | **not in notebook** | Overview map + Compare → Factor geography (new) |

## Problems found in the notebook, and how the app handles them

1. **"Total injuries by borough" chart does not show totals.** The table (cell 18) sums injuries; the plot (cell 19)
   uses `sns.barplot` on the raw column, which plots the *mean injured per crash* with bootstrapped error bars
   (also very slow on 2M rows). The title says "Average…", but the section heading asks for "most injuries".
   *App:* people injured is a KPI and table column; the borough charts show crash counts and injury **rate**.
2. **Partial years are plotted as if comparable.** The data starts 2012‑07‑01 (2012 has 100,545 crashes vs ~204k in 2013)
   and ends in mid‑2025 (33,612 crashes). Both are partial and produce misleading "growth" and "collapse" at the
   ends of the time-series and injury-by-road-user charts.
   *App:* partial years are detected from the data, excluded from the default year range, and drawn as open diamonds.
3. **The `< 2025` filter does nothing.** In cell 44/45 the line `injuries_over_time = injuries_over_time[... < 2025]`
   runs *after* `plt.show()`, so the plotted data still includes 2025 (and it never removes 2012 anyway).
4. **Missing injury/fatality values are counted as "no injury".** `NUMBER OF PERSONS INJURED` has 18 missing and
   `…KILLED` has 31. `x > 0` is `False` for NaN, so they land in the denominator as non-injury crashes.
   (Tiny here, but it is the wrong principle.) *App:* rates use only rows where the outcome is recorded.
5. **Borough "Unknown" is 30.8% of rows and is silently dropped from borough charts**, so every borough count and
   rate is based on ~69% of crashes. *App:* an explicit callout, an "Unknown" row in the table so totals reconcile,
   missingness-by-year in Data & Methods, and an optional fill-from-coordinates mode (needs a boundary file).
6. **Invalid coordinates exist.** `describe()` shows latitude min `0.0`, longitude min `-201.36` and max `0.0`.
   *App:* coordinates outside a NYC rectangle become missing; they are never replaced with invented locations.
7. **Factor analysis only looks at `CONTRIBUTING FACTOR VEHICLE 1`**, and 733,070 rows (33.6%) are "Unspecified".
   *App:* labelled everywhere; optional "any vehicle" mode counts each crash once per factor; the Unspecified share
   is shown for every selection.
8. **Source label quirks.** The data contains `Illnes` (typo) and very long labels; case-variant duplicates and
   numeric junk codes are common in this dataset. *App:* typo fixed, case variants merged, numeric codes excluded
   (all counted in the prep report).
9. **Rates compared without uncertainty.** Hourly and factor rates are shown as lines/bars with no indication of
   how few crashes some points rest on. *App:* 95% Wilson intervals, minimum-count thresholds.
10. **Minor:** `CRASH DATE` is parsed without a format (`format="%m/%d/%Y"` is faster and unambiguous); column 3
    (ZIP) triggers a `DtypeWarning` (not needed by the app, so it is not loaded).

## Things in the brief that don't match the data
- The brief says "2010–2025". The file's first records are **July 2012**; the app reads the real range from the data.

## Implementation notes
- One row per crash is kept in a compact Parquet file; every filter is a NumPy boolean mask, so the map, KPIs and
  charts always agree. Factors and vehicle types are bit masks so a crash is counted once per category.
- The browser never receives individual crashes — only aggregated grid cells.
