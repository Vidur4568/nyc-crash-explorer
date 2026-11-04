"""Normalise an NYC borough-boundary GeoJSON for the app.

Usually you do not run this directly: `python scripts/download_boundaries.py`
downloads the file and calls `normalize()` for you. Run this only if you
downloaded the GeoJSON by hand:

    python scripts/prepare_boundaries.py --src path/to/boroughs.geojson

Output: data/processed/nyc_boroughs.geojson with a `borough` property
(BRONX, BROOKLYN, MANHATTAN, QUEENS, STATEN ISLAND). The input MUST be in
longitude/latitude degrees (EPSG:4326).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils.schema import BOROUGHS  # noqa: E402

NAME_KEYS = {"boroname", "boro_name", "borough", "boro", "name"}
CODE_KEYS = {"borocode", "boro_code", "borough_code"}
CODE_MAP = {"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN", "4": "QUEENS", "5": "STATEN ISLAND"}


def _coords(c):
    if isinstance(c[0], (int, float)):
        yield c
    else:
        for x in c:
            yield from _coords(x)


def _borough_name(props: dict):
    lower = {str(k).lower(): v for k, v in props.items()}
    for k in NAME_KEYS:
        if k in lower and str(lower[k]).strip().upper() in BOROUGHS:
            return str(lower[k]).strip().upper()
    for k in CODE_KEYS:
        if k in lower and str(int(float(lower[k]))) in CODE_MAP:
            return CODE_MAP[str(int(float(lower[k])))]
    return None


def normalize(src: Path, out: Path) -> Path:
    gj = json.loads(Path(src).read_text())
    feats = []
    for ft in gj.get("features", []):
        name = _borough_name(ft.get("properties", {}))
        if name is None:
            sys.exit(f"Could not recognise a borough in properties: {ft.get('properties')}")
        pts = list(_coords(ft["geometry"]["coordinates"]))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        if not (-75 < min(xs) and max(xs) < -73 and 40 < min(ys) and max(ys) < 41.5):
            sys.exit("Coordinates are not lon/lat degrees (EPSG:4326). Re-export the GeoJSON in EPSG:4326.")
        feats.append({"type": "Feature", "properties": {"borough": name}, "geometry": ft["geometry"]})
    found = sorted({f["properties"]["borough"] for f in feats})
    if found != sorted(BOROUGHS):
        sys.exit(f"Expected the 5 boroughs, found {found}")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return Path(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=ROOT / "data/raw/nyc_boroughs_raw.geojson")
    ap.add_argument("--out", type=Path, default=ROOT / "data/processed/nyc_boroughs.geojson")
    a = ap.parse_args()
    if not a.src.exists():
        sys.exit(f"Not found: {a.src}\nRun scripts/download_boundaries.py, or download the GeoJSON by hand (see docstring).")
    out = normalize(a.src, a.out)
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.2f} MB). Restart the app to enable borough clicking.")


if __name__ == "__main__":
    main()
