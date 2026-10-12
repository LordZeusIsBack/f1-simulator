"""Download the V6 reference data from the Jolpica-F1 API (Ergast-compatible) into data/reference/raw/.

Needs internet; run it only to refresh the data. Everything else in validation/ works offline from the saved files.
Data licence: CC BY-NC-SA 4.0 (jolpica-f1 / Ergast). See data/reference/README.md.

    python3 -m validation.fetch_reference
"""
import json
import time
import urllib.request
from pathlib import Path

API = "https://api.jolpi.ca/ergast/f1"
RAW = Path(__file__).resolve().parent.parent / "data" / "reference" / "raw"
SEASONS = (2024, 2025)
ROUND = 16  # Italian Grand Prix at Monza in both seasons (checked below)
TEAMS = ("Red Bull", "Ferrari", "McLaren", "Mercedes")  # the constructors cars.py has a model car for


def get(path: str) -> bytes:
    with urllib.request.urlopen(f"{API}/{path}", timeout=30) as response:
        body = response.read()
    time.sleep(0.5)  # well under the API's 4 requests/s burst limit
    return body


def save(name: str, body: bytes) -> dict:
    (RAW / name).write_bytes(body)  # stored exactly as downloaded
    return json.loads(body)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for season in SEASONS:
        for kind in ("qualifying", "results", "pitstops"):
            data = save(f"{season}_{kind}.json", get(f"{season}/{ROUND}/{kind}.json?limit=100"))
            circuit = data["MRData"]["RaceTable"]["Races"][0]["Circuit"]["circuitId"]
            if circuit != "monza":
                raise RuntimeError(f"{season} round {ROUND} is {circuit}, not monza")
        results = json.loads((RAW / f"{season}_results.json").read_bytes())
        for result in results["MRData"]["RaceTable"]["Races"][0]["Results"]:
            if result["Constructor"]["name"] in TEAMS:
                driver = result["Driver"]["driverId"]
                save(f"{season}_laps_{driver}.json", get(f"{season}/{ROUND}/drivers/{driver}/laps.json?limit=100"))
    print(f"saved {len(list(RAW.glob('*.json')))} files to {RAW}")


if __name__ == "__main__":
    main()
