# Reference data (V6 validation)

Real, public Formula 1 timing data for the **2024 and 2025 Italian Grands Prix (Monza, round 16 in both seasons)**. It is used only by `validation/`; the simulator never reads it.

## Source and licence

- **Source:** the Jolpica-F1 API, an open-source, volunteer-run successor to the Ergast API, with the same response format. Ergast-compatible endpoint: `https://api.jolpi.ca/ergast/f1/`. Project: https://github.com/jolpica/jolpica-f1
- **Accessed:** 2026-10-12, with `python3 -m validation.fetch_reference`.
- **Licence:** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0), per the Jolpica-F1 Terms of Use (last updated 2025-08-27): https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md
  - **Non-commercial use only.**
  - Credit "Jolpica-F1 / Ergast".
  - Anything derived from this data must use the same licence.

  This licence applies to the files in this folder, not to the project's code: see [LICENSE.md](LICENSE.md) and the repository's [NOTICE](../../NOTICE).
- **Disclaimer from the source:** the data comes with no guarantee of correctness or availability. The API is rate-limited (4 requests/s burst, 500/hour). The fetch script waits 0.5 s between requests.

## Files (`raw/`, stored byte-for-byte as downloaded)

| File | Endpoint | Content |
|---|---|---|
| `{season}_qualifying.json` | `/{season}/16/qualifying.json?limit=100` | Q1, Q2 and Q3 lap times per driver, as text `m:ss.sss` |
| `{season}_results.json` | `/{season}/16/results.json?limit=100` | Classification: laps, total time (`millis`), each driver's fastest lap (`m:ss.sss`). For **2024 only**, the fastest lap's average speed in **kph**. |
| `{season}_pitstops.json` | `/{season}/16/pitstops.json?limit=100` | Pit stops: driver, lap, stop number, pit-lane `duration` in s (not used, see below) |
| `{season}_laps_{driverId}.json` | `/{season}/16/drivers/{driverId}/laps.json?limit=100` | That driver's 53 race lap times (`m:ss.sss`). Only the 8 drivers of the four teams the model has cars for: Red Bull, Ferrari, McLaren and Mercedes. |

That makes 22 files and about 190 KB. Seasons: 2024 and 2025.

## Transformations

All transformations happen in `validation/reference.py`, at load time. Nothing processed is stored.

| Quantity | Transformation | Unit |
|---|---|---|
| Lap times | `m:ss.sss` text → seconds (e.g. `1:19.327` → 79.327) | s |
| Race time | `millis` ÷ 1000 | s |
| Speed | kph ÷ 3.6 | m/s |
| Track length | median over drivers of (fastest-lap average speed × fastest-lap time). 2024 only, because 2025 has no average speeds. | m |
| Team best qualifying lap | fastest Q1, Q2 or Q3 time of either team driver | s |
| Pit loss per stop | (in-lap + out-lap) − 2 × median of the driver's clean laps within 5 laps of the stop. "Clean" excludes lap 1, all in- and out-laps, and laps above 107 % of the driver's race median. A stop with fewer than 3 clean laps is skipped. | s |

## Known limitations of this data

- **No tyre compounds,** no telemetry, no speeds through corners, no fuel loads and no car set-up. Strategy comparisons therefore have to assume compounds.
- **The pit-stop `duration`** is time spent in the pit lane, not time *lost* compared with driving past. The model's `pit_loss` means the latter, so the loss is measured from the lap times instead.
- **Two races at one circuit.** Results say nothing about other tracks.
- **The four model cars** (`cars.py`) are placeholders named after teams. They are not those teams' real cars, and their parameters were never derived from data.
