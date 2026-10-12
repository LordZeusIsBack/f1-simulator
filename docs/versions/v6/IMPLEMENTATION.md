# V6: Calibration and validation (implementation)

## 1. Objective and scope

V6 adds no simulator features. It measures how far the existing model is from real Formula 1 data, in a repeatable way:

- an **audit** of every model parameter: where it comes from, and how much evidence supports it;
- a **small real reference dataset**: the 2024 and 2025 Italian Grands Prix at Monza, from the public Jolpica-F1 (Ergast-compatible) API;
- a **workflow:** load and check data → preprocess → run the simulator → compute metrics → write a report;
- a **calibration** of two parameters on 2024, evaluated on 2025 (held out), with the original values kept as the baseline;
- an honest list of what can and cannot be validated with this data.

**The simulator code is unchanged.** The calibrated values are **not** written into it. They live in `validation/config/calibrated.json` and are passed to the simulator only by the validation tooling.

## 2. What was added

| Path | Role |
|---|---|
| `data/reference/raw/*.json` | 22 raw API responses, byte-for-byte as downloaded (real data) |
| `data/reference/README.md` | Provenance: source, URLs, access date, licence, units, transformations, limitations |
| `validation/fetch_reference.py` | Downloads the raw data. This is the only part that uses the network. |
| `validation/reference.py` | Loads and checks the raw files; converts them to SI numbers |
| `validation/metrics.py` | Error metrics |
| `validation/model.py` | Runs the simulator for a configuration (parameters passed in, nothing global changed) |
| `validation/config/baseline.json` | The V0–V5 parameter values |
| `validation/config/calibrated.json` | Fitted values and how they were fitted (generated) |
| `validation/calibrate.py` | Fits the calibrated values on 2024 only |
| `validation/evaluate.py` | Compares both configurations with 2024 and 2025 and writes the report |
| `validation/reports/validation_report.md` | The generated report |
| `test_validation.py` | Tests for the above |
| `test_race_control.py` | + V5 regression test |

## 3. Separation

```
data/reference/raw/        source data (never edited)
        │  validation/reference.py   load, check, convert, derive
        ▼
reference numbers ──────────────┐
                                │
validation/config/*.json ──► validation/model.py ──► simulator (cars, tracks, physics, race: unchanged)
   (baseline, calibrated)       │
                                ▼
                     validation/metrics.py ──► validation/evaluate.py ──► reports/validation_report.md
validation/calibrate.py: reference 2024 + model ──► config/calibrated.json
```

Source data, processing code, configuration and simulation code are in separate places. The simulator does not import anything from `validation/` or `data/`.

## 4. Data provenance (summary)

Full details are in [`data/reference/README.md`](../../../data/reference/README.md).

- **Source:** the Jolpica-F1 API, `https://api.jolpi.ca/ergast/f1/`. It continues the Ergast API in the same format. Accessed 2026-10-12.
- **Licence:** CC BY-NC-SA 4.0: non-commercial use only, with attribution, and share-alike for derived data. The source gives no guarantee of correctness.
- **Content:**
  - Monza 2024 and 2025 qualifying results;
  - race classifications;
  - pit stops;
  - race lap times for the 8 drivers of the four modelled teams (Red Bull, Ferrari, McLaren, Mercedes).
- **Not in the data:** tyre compounds, telemetry (speeds, throttle, braking), fuel loads, car parameters.

## 5. Parameter provenance audit

Evidence levels:

- **Physical:** a physical constant or standard value.
- **Regulation:** taken from the F1 sporting or technical rules as commonly reported. Not re-checked against FIA documents in V6.
- **Numerical:** a resolution or tolerance, not a physical claim.
- **Estimate:** an order-of-magnitude guess, plausible but unverified.
- **Placeholder:** chosen to make behaviour visible; no evidence.
- **V6 data:** compared with the reference data in this version.

| Parameter | Where | Value | Level | V6 finding |
|---|---|---|---|---|
| `G` | physics.py | 9.81 m/s² | Physical | — |
| `AIR_DENSITY` | physics.py | 1.225 kg/m³ | Physical (sea-level standard; real Monza air differs a little) | — |
| `TYRE_GRIP` | physics.py | 1.8 | Placeholder | **V6 data:** a zero-bias fit needs 2.94, which is implausible as a real friction coefficient. The baseline car is 15–16 s/lap too slow (§10). |
| `STEP` | simulation.py | 1 m | Numerical | — |
| `power` | cars.py | 740–750 kW | Estimate (magnitude of a modern F1 power unit) | not validated (no data) |
| `drag` (C_D·A) | cars.py | 1.18–1.25 m² | Placeholder | not validated |
| `downforce` (C_L·A) | cars.py | 3.2–3.9 m² | Placeholder | not validated |
| `mass` | abstract_classes.py | 800 kg | Regulation (close to the 798 kg minimum incl. driver, 2023–2025) | — |
| Team differences between the 4 cars | cars.py | — | Placeholder | **V6 data:** they predict McLaren fastest in both years; the real fastest was McLaren in 2024 and Red Bull in 2025 |
| Monza segments (lengths, radii, gradients) | tracks.py | total 5 900 m | Estimate | **V6 data:** total length +107 m (+1.85 %) against the 5 793 m derived from the data. Radii not verifiable (no telemetry). |
| `GRID_SPACING` | race.py | 8 m | Estimate | not validated |
| `PIT_LOSS` | race.py | 22 s | Placeholder | **V6 data:** measured median 25.62 s (2024, 14 stops) and 25.36 s (2025, 8 stops). The baseline is about 3.5 s too low. |
| `FUEL_PER_LAP` | race.py | 1.9 kg | Estimate (≈ 100 kg over a 53-lap race) | not validated (no fuel data) |
| `FUEL_CAPACITY` | race.py | 110 kg | Regulation (maximum race fuel 2019–2025) | — |
| `REFUEL_RATE` | race.py | 10 kg/s | Placeholder (refuelling banned since 2010) | — |
| `FUEL_TOLERANCE`, `WETNESS_STEP` | race.py | 1e-9 kg, 0.05 | Numerical | — |
| Compound `grip`, `wear_per_lap`, `wet_loss`; `WORN_GRIP_LOSS` | tyres.py | see V2/V4 | Placeholder | not validated (no compound data) |
| `PACE_SPREAD` | drivers.py | 0.01 | Placeholder | not validated |
| `min_gap`, `dirty_air_*`, `drs_min_straight`, `drs_gain`, `overtake_margin`, `racecraft_effect` | traffic.py | see V3 | Placeholder | not validated |
| `drs_interval` 1.0 s, `drs_from_lap` 3 | traffic.py | | Regulation (the 1-second DRS rule; DRS enabled from the third lap) | — |
| `SUN_HEATING`, `WETTING_RATE`, `DRYING_RATE`, `DRYING_MIN_TEMP` | weather.py | see V4 | Placeholder | not validated (both races were dry) |
| `WEATHER_MARGIN` | strategy.py | 0.05 | Placeholder | — |
| `yellow_slowdown`, `vsc_factor`, `sc_*`, `drive_through_loss`, `two_compound_penalty`, `drs_max_wetness` | race_control.py | see V5 | Placeholder (`two_compound_penalty` is a stated model choice) | not validated (no SC, VSC or penalties in the reference races) |

## 6. What can and cannot be validated with this data

| Aspect | Validated in V6? | Why |
|---|---|---|
| Track length | **yes** | Average speed × time of the fastest lap gives the lap length (2024) |
| Single-lap pace (V0 flying lap) | **yes**, per team | Best qualifying laps are the closest real equivalent: low fuel, new tyres, flying lap |
| Pit loss | **yes** | Measured from lap times around stops |
| Total race time | **partly** | One car alone in the model against the real winner in traffic, with a standing start and unknown compounds |
| Corner speeds, braking points, top speed | no | No telemetry in the data |
| Tyre compounds, wear, degradation | no | No compound data; tyre effects are mixed with fuel in lap times |
| Fuel effect | no | No fuel data |
| Traffic, overtaking, DRS | no | Possible in future from per-lap positions; not attempted |
| Weather | no | Both races were dry |
| Race control | no | No SC, VSC or penalties of the modelled kind in these races |
| Other circuits | no | Only Monza is modelled and collected |

## 7. Metrics

Error = model − reference, so a positive error means the model is slower or longer. Defined in `validation/metrics.py`:

| Metric | Formula |
|---|---|
| error | m − r |
| relative error | (m − r) / r (rejects r = 0) |
| mean error (bias) | Σ(mᵢ − rᵢ) / n |
| MAE | Σ\|mᵢ − rᵢ\| / n |
| MAPE | 100 × Σ\|mᵢ − rᵢ\| / \|rᵢ\| / n |
| max \|error\| | max \|mᵢ − rᵢ\| |

## 8. The four checks

| Check | Reference side | Model side |
|---|---|---|
| Track length | median over drivers of the fastest lap's average speed (kph ÷ 3.6) × its time (2024: 5 793.0 m) | `Monza().length` = 5 900 m |
| Qualifying pace | each modelled team's fastest Q1, Q2 or Q3 lap (either driver) | `simulate_lap(CARS[team], Monza(), tyre_grip)`: no fuel, flying lap |
| Pit loss | for each stop by a modelled-team driver: (in-lap + out-lap) − 2 × the median clean lap within ±5 laps (rules in the data README) | the configured `pit_loss` |
| Race time | the winner's total time, laps and stop laps | the winner team's model car racing **alone** for the same laps, stopping on the same laps, medium then hard (**assumed**: the data has no compounds), grips scaled by `tyre_grip / 1.8` |

## 9. Calibration procedure

| Parameter | Method | Fitted on |
|---|---|---|
| `tyre_grip` | Bisection on [1.0, 5.0] to 10⁻⁴ for the value where the **mean** error of the four cars' flying laps is zero. Lap time falls steadily as grip rises, so there is exactly one solution if any. | 2024 qualifying (4 laps) |
| `pit_loss` | Median of the measured stops (robust to the one slow stop, 34.85 s) | 2024 (14 stops) |

- **Train/test split:** calibration reads only `2024_*` files. 2025 is held out and is reported separately as "held out".
- **Disclosure:** both seasons are the **same circuit** under the **same technical regulations** (2022–2025). The held-out test is therefore a test across years at one track, not across tracks. There are only 4 qualifying laps and 8 to 14 stops per season.
- **Baseline preserved:** `baseline.json` equals the code constants (a test checks this). `calibrated.json` records the baseline values next to the fitted ones.
- **Reproducible:** no randomness and no timestamps. A test re-runs the calibration and requires it to equal the committed `calibrated.json`.

**What the fitted `tyre_grip` means.** 2.94 is not a tyre property. Real tyre friction coefficients are well below that. It is an **effective** parameter that absorbs every other error in the lap model: the track is 107 m too long, the corner radii are rough, and the car's power, drag and downforce values are placeholders. It makes the lap **time** right, not the physics.

## 10. Results

Full numbers are in [`validation/reports/validation_report.md`](../../../validation/reports/validation_report.md).

| Check | Baseline | Calibrated, 2024 (training) | Calibrated, 2025 (held out) |
|---|---|---|---|
| Track length | +107 m (+1.85 %), both configs | — | — |
| Qualifying MAE / bias | 15.29 s / +15.29 s (2024); 15.80 s / +15.80 s (2025) | 0.370 s / 0.000 s | **0.516 s / +0.516 s** |
| Qualifying fastest team | model McLaren; real McLaren (2024), Red Bull (2025) | correct | **wrong** (model McLaren, real Red Bull) |
| Pit loss: error against the measured median | −3.62 s (2024), −3.36 s (2025) | 0.00 s | **+0.26 s** (MAE 0.98 s against individual stops) |
| Race time | +693 s (+15.5 %) 2024; +739 s (+16.8 %) 2025 | −118 s (−2.6 %) | **−91 s (−2.1 %)** |

### Validated findings (supported by the data)

1. **The baseline lap model is about 15–16 s (19–20 %) too slow** at Monza, for all four cars, in both years.
2. **The modelled Monza is 107 m too long** (5 900 m against 5 793 m).
3. **The baseline pit loss of 22 s is about 3.5 s too low.** Measured Monza stops cost a median of 25.4–25.6 s.
4. **With one effective grip value fitted to 2024, the 2025 qualifying laps are matched within 0.82 s** (MAE 0.52 s). The model is 0.5 s slow on average, because the real 2025 cars were faster. The fixed car parameters cannot express that change, and they get the fastest team wrong.
5. **The calibrated model races 2–3 % too fast** over a full race. Real race laps are about 4–5 s slower than qualifying laps; for example, the 2024 median race lap is about 83.7 s against qualifying laps around 79.3 s. The model's fuel and tyre effects reproduce less of that gap. This conclusion comes from total race time only. The model car also runs without traffic and with a rolling start, so the split between causes is **not** established.

### Unverified assumptions (unchanged by V6)

- All tyre, fuel-burn, traffic, DRS, weather and race-control parameters: the data cannot test them.
- The car parameters (power, drag, downforce) individually. Only their combined effect on lap time was measured.
- The compounds in the race-time check (medium → hard) are assumed.

### Synthetic material

Synthetic data appears **only** in `test_validation.py`: small invented files and lap lists that test error handling and arithmetic. They are labelled `SYNTHETIC`, are written to temporary folders, and are never used for any reported result.

## 11. Limitations of the validation itself

- **Small sample:** two races at one track, four teams, 22 stops.
- **One track and adjacent years:** the held-out test does not show the model generalises to other circuits.
- **Imperfect reference equivalents:**
  - best qualifying laps include driver differences and track evolution;
  - measured pit loss includes slow stops and the out-lap on cold tyres;
  - the winner's race time includes a standing start and traffic.
- **The data source** is volunteer-run and makes no guarantee of correctness. It agrees with widely published results, for example the 2024 pole of 1:19.327 and the 5.793 km lap length.
- **The calibrated values are not adopted.** Changing the simulator defaults would change every V0–V5 regression value. That is a decision for later, and a calibrated grip of 2.94 should not be read as physics.

## 12. Reproducing

```bash
python3 -m validation.fetch_reference   # optional: re-download (needs internet; data may have been corrected upstream)
python3 -m validation.calibrate          # rewrites validation/config/calibrated.json (2024 only)
python3 -m validation.evaluate           # rewrites validation/reports/validation_report.md and prints it
python3 test_validation.py               # includes "report is up to date" and "calibration reproduces"
```
