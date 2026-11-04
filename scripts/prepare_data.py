"""Turn the raw NYC collisions CSV into the compact files the app loads.

    python scripts/prepare_data.py                      # full file
    python scripts/prepare_data.py --sample 100000      # quick test run
    python scripts/prepare_data.py --csv path/to/file.csv

Outputs (in data/processed/):
    crashes.parquet   one row per crash, ~25 narrow numeric columns
    meta.json         category lists, partial years, data-quality report

Run this ONCE. The Streamlit app never reads the big CSV.
Memory: loading the 2.18M-row CSV needs a few GB of RAM while this runs
(estimate - not measured on your machine). Close other apps if it struggles,
or test with --sample first.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.prepare import transform_raw                      # noqa: E402
from utils.schema import RAW_REQUIRED_COLS                   # noqa: E402

DEFAULT_CSV = ROOT / "data" / "raw" / "Motor_Vehicle_Collisions_-_Crashes_20250603.csv"
DEFAULT_BOUNDS = ROOT / "data" / "processed" / "nyc_boroughs.geojson"
OUT_DIR = ROOT / "data" / "processed"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--sample", type=int, default=0, help="use a random sample of N rows (testing)")
    ap.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDS,
                    help="borough GeoJSON from scripts/prepare_boundaries.py (optional)")
    ap.add_argument("--dry-run", action="store_true", help="run the cleaning + report, write nothing")
    args = ap.parse_args()

    if not args.csv.exists():
        sys.exit(f"CSV not found: {args.csv}\nPut the Kaggle file in data/raw/ or pass --csv.")

    t0 = time.time()
    print(f"Reading {args.csv.name} (only the columns the app needs)...")
    raw = pd.read_csv(args.csv, usecols=RAW_REQUIRED_COLS, low_memory=False)
    print(f"  {len(raw):,} rows read in {time.time() - t0:.0f}s")
    if args.sample:
        raw = raw.sample(min(args.sample, len(raw)), random_state=1).reset_index(drop=True)
        print(f"  using a random sample of {len(raw):,} rows")

    bounds = args.boundaries if args.boundaries.exists() else None
    print("Boundaries:", bounds if bounds else "none found -> boroughs stay as reported (31% 'Unknown' expected)")
    print("Cleaning...")
    out, meta = transform_raw(raw, boundaries_path=bounds)
    del raw

    q = meta["quality"]
    print("\n=== DATA-QUALITY REPORT ===")
    print(f"Date range           : {meta['date_min']} -> {meta['date_max']}")
    print(f"Partial years        : {meta['partial_years']}  (excluded from default annual comparisons)")
    print(f"Rows raw -> final    : {q['rows_raw']:,} -> {q['rows_final']:,}  "
          f"(dup ids dropped: {q['duplicate_collision_ids_dropped']}, bad dates: {q['rows_dropped_bad_date']})")
    print(f"Borough missing      : {q['borough_missing_pct']}%")
    print(f"Valid coordinates    : {q['coords_valid_pct']}%  "
          f"(present-but-invalid: {q['coords_present_but_invalid']:,}, missing: {q['coords_missing']:,})")
    print(f"Injury/killed missing: {q['persons_injured_missing']} / {q['persons_killed_missing']} rows")
    print(f"Factor (vehicle 1)   : {q['factor1_usable_pct']}% usable, "
          f"{q['factor1_unspecified_or_missing_pct']}% Unspecified/missing; {q['n_factor_categories']} categories")
    print(f"Vehicle groups       : {q['vehicle_any_group_pct']}% of crashes have a type; "
          f"{q['vehicle_other_group_share_pct']}% of type entries fell in 'Other'")
    if "borough_derived_from_coords" in q:
        print(f"Borough derived      : {q['borough_derived_from_coords']:,} rows; agreement with reported "
              f"borough {q.get('borough_reported_vs_derived_agreement_pct')}%")
    print("\nTop raw vehicle-type values and the group they were assigned to (REVIEW THIS):")
    for r in meta["vehicle_audit_top40"][:25]:
        print(f"  {r['count']:>9,}  {r['raw'][:42]:<42} -> {r['group']}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_DIR / "crashes.parquet", index=False, compression="zstd")
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    mb = (OUT_DIR / "crashes.parquet").stat().st_size / 1e6
    print(f"\nWrote data/processed/crashes.parquet ({mb:.0f} MB) and meta.json in {time.time() - t0:.0f}s")
    if mb > 95:
        print("WARNING: file is near GitHub's 100 MB limit; see README 'Deployment' for options.")


if __name__ == "__main__":
    main()
