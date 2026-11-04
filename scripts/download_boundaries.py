"""Download NYC borough boundaries and prepare them for the app (one command).

    python scripts/download_boundaries.py

Source: NYC Department of City Planning, "Borough Boundaries (Clipped to
Shoreline)", served as an ArcGIS feature service. Standard library only.

NOTE: the endpoint below was located via search but could not be test-called
from the environment this script was written in. If it fails, the script
prints manual steps: download the GeoJSON (EPSG:4326) from
https://www.nyc.gov/site/planning/data-maps/open-data/districts-download-metadata.page
into data/raw/nyc_boroughs_raw.geojson and run scripts/prepare_boundaries.py.
Geometry is lightly simplified (~20 m) to keep the file small for the browser.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_boundaries import normalize  # noqa: E402

RAW = ROOT / "data" / "raw" / "nyc_boroughs_raw.geojson"
OUT = ROOT / "data" / "processed" / "nyc_boroughs.geojson"
SERVICE = "NYC_Borough_Boundary_b17b9_52b1c"
CANDIDATES = [
    f"https://services-nocdn.arcgis.com/P3ePLMYs2RVChkJx/ArcGIS/rest/services/{SERVICE}/FeatureServer/0/query",
    f"https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/{SERVICE}/FeatureServer/0/query",
]
PARAMS = {"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326",
          "geometryPrecision": "5", "maxAllowableOffset": "0.0002", "f": "geojson"}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(PARAMS),
                                 headers={"User-Agent": "nyc-crash-explorer/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    if len(data.get("features", [])) < 5:
        raise RuntimeError(f"expected 5 borough features, got {len(data.get('features', []))}")
    return data


def main() -> None:
    last = None
    for url in CANDIDATES:
        try:
            print("Trying", url.split("/rest/")[0])
            data = fetch(url)
            RAW.parent.mkdir(parents=True, exist_ok=True)
            RAW.write_text(json.dumps(data))
            out = normalize(RAW, OUT)
            print(f"Done: {out} ({out.stat().st_size / 1e6:.2f} MB).\n"
                  "Restart the app to enable borough clicking. To also FILL missing boroughs from coordinates, "
                  "re-run: python scripts/prepare_data.py")
            return
        except Exception as e:                              # noqa: BLE001
            last = e
            print("  failed:", e)
    sys.exit(f"\nCould not download automatically ({last}).\nManual route:\n"
             "  1. Download 'Borough Boundaries (Clipped to Shoreline)' as GeoJSON (EPSG:4326) from\n"
             "     https://www.nyc.gov/site/planning/data-maps/open-data/districts-download-metadata.page\n"
             f"  2. Save it as {RAW}\n  3. python scripts/prepare_boundaries.py")


if __name__ == "__main__":
    main()
