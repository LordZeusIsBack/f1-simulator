# V4 changelog: weather and changing track conditions

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V3) | `07bb68e` "docs(v3): record version commit hash in changelog" (V3 code is in `9fb0290`) |
| V4 version commit | `PENDING` |
| Commit message | `feat(v4): add weather and changing track conditions` |

As in earlier versions, the hash is recorded by a follow-up commit, `docs(v4): record version commit hash in changelog`, which changes only this table.

Line numbers refer to the V4 version commit and may shift later.

## How V4 differs from V3

| V3 | V4 |
|---|---|
| The track is always dry | An optional scripted `Weather` (air temperature, rain) drives a smoothly changing track wetness |
| Grip comes from the compound, wear and fuel (via mass) | Grip is also multiplied by `1 − wet_loss × wetness` |
| Only dry compounds (soft, medium, hard) are accepted | Intermediates and wets are in the default `COMPOUNDS`; `DRY_COMPOUNDS` keeps V2's set |
| Lap profiles change only at the line | They are also rebuilt mid-lap when wetness moves by 0.05 or more |
| Strategies are fixed plans | A plan can opt in to `react_to_weather` and pit for the best compound |
| Logs: `pit_events`, `overtakes` | Plus `weather_events` ("rain starts", "rain stops", "best tyres") |
| — | `Race(weather=None)` (the default) and a no-rain timeline both reproduce V3 exactly |

## Files

| File | Origin | V4 status |
|---|---|---|
| `weather.py` | — | **new** |
| `test_weather.py` | — | **new** |
| `docs/versions/v4/*.md` | — | **new** |
| `tyres.py` | V2 | modified |
| `strategy.py` | V2 | modified |
| `race.py` | V1–V3 | modified |
| `test_tyres_fuel_pits.py` | V2, V3 | modified (2 tests now pass V2's dry-only table) |
| `test_traffic.py` | V3 | modified (V3 regression test added) |
| `README.md` | V1–V3 | modified |
| `abstract_classes.py`, `cars.py`, `tracks.py`, `physics.py`, `simulation.py`, `drivers.py`, `traffic.py`, `main.py`, `test_simulation.py`, `test_race.py`, `pyproject.toml`, `uv.lock`, `docs/versions/v1–v3/*` | | **unchanged** |
| Removed files | | none |

`abstract_classes.TyreCompound` is unchanged. Its existing INTERMEDIATE and WET members are now used.

## Changes per file

### `weather.py` (new, 81 lines)

| Symbol | Lines | Behaviour |
|---|---|---|
| `AIR_TEMP_RANGE`, `MAX_RAIN` | 5–6 | accepted ranges: −10 to 50 °C, 0 to 50 mm/h |
| `SUN_HEATING`, `WETTING_RATE`, `DRYING_RATE`, `DRYING_MIN_TEMP` | 7–10 | 15 °C, 0.001 /s per mm/h, 3·10⁻⁵ /s per °C, 0 °C (placeholders) |
| `WeatherPoint` (frozen) | 13–26 | `time` (s), `air_temp` (°C), `rain` (mm/h), validated in `__post_init__` |
| `Conditions` (frozen) | 29–36 | `time`, `air_temp`, `track_temp`, `rain`, `wetness` |
| `Weather.__init__` | 42–51 | validates the timeline (non-empty, strictly increasing) and the starting wetness (0–1) |
| `Weather._scripted` | 53–63 | air temperature and rain at a time: held, or linearly interpolated |
| `Weather.conditions` (property) | 65–68 | current `Conditions`; track temperature = air + 15 × (1 − W) |
| `Weather.advance(dt)` | 70–81 | exact relaxation of W towards k_wet / (k_wet + k_dry), rates frozen at the start of the step |

### `tyres.py` (modified)

| Symbol | Lines | Before (V2) | After (V4) |
|---|---|---|---|
| `Compound` | 10–13 | `grip`, `wear_per_lap` | adds `wet_loss: float = 0.0` |
| `DRY_COMPOUNDS` | 18–22 | — (was `COMPOUNDS`) | V2's three slicks, now each with `wet_loss = 0.65` |
| `COMPOUNDS` | 23–27 | soft, medium, hard | `DRY_COMPOUNDS` plus INTERMEDIATE (1.55, 0.03, 0.32) and WET (1.35, 0.03, 0.15) |
| `Tyres.grip` | 40–42 | `(compounds)` | `(compounds, wetness=0.0)`: also × (1 − wet_loss × wetness). With wetness 0 it is bit-for-bit V2's value. |
| `best_compound` | 45–47 | — | new: the compound with the most new-set grip at a wetness |

### `strategy.py` (modified)

| Symbol | Lines | Before (V2) | After (V4) |
|---|---|---|---|
| `WEATHER_MARGIN` | 6 | — | 0.05 |
| `Strategy.react_to_weather` | 26 | — | new field, default `False` |
| `Strategy.planned_stop(lap)` | 28–29 | (was the body of `stop_after`) | the planned stop only. Used by the race's fuel check. |
| `Strategy.stop_after(lap, tyres, wetness, compounds)` | 31–46 | `(lap)`: planned stop | the planned stop, else (if reacting) `PitStop(lap, best)` when best's grip > current × 1.05 |

### `race.py` (modified, 334 → 368 lines)

| Symbol | Lines | Change |
|---|---|---|
| imports | 13–14 | adds `best_compound`, `Conditions`, `Weather` |
| `WETNESS_STEP` | 22 | new: 0.05 |
| `WeatherEvent` (frozen) | 56–61 | new: `time`, `kind`, `conditions`, `best` |
| `Race.__init__` | 118–168 | new `weather=None` setting. Rejects a used `Weather`. Adds `self.weather`, `weather_events`, `_grip_wetness`. |
| `Race._check` | 170–200 | the fuel check uses `strategy.planned_stop(lap)`, not `stop_after` |
| `Race._profile` | 202–203 | grip uses `_grip_wetness` |
| `Race.step` | 212–230 | refreshes all running cars' profiles when wetness has moved ≥ 0.05; after moving the cars, calls `_update_weather` |
| `Race._update_weather` | 232–240 | new: advances the weather and logs rain start/stop and best-compound changes |
| `Race._complete_lap` | 336–348 | asks `stop_after(laps, tyres, wetness, compounds)` |

### `test_tyres_fuel_pits.py` (modified)

| Change | Lines | Why |
|---|---|---|
| imports `DRY_COMPOUNDS` | 10 | — |
| `test_dry_compounds_start_new_and_wet_ones_are_rejected` | 25–35 | Its rejection loop now passes `compounds=DRY_COMPOUNDS`. It still checks V2's rule that a compound outside the race's table is rejected; since V4 the default table includes wet tyres. |
| `test_impossible_pit_plans_are_rejected` | 99–120 | passes `compounds=DRY_COMPOUNDS`, for the same reason (the WET-stop case). All 13 cases are kept. |

### `test_traffic.py` (modified)

| Change | Lines | Why |
|---|---|---|
| `test_v3_race_results_unchanged_without_weather` | 192–201 | new regression test: a 3-car, 6-lap traffic race with a stop. Finish times and the overtake log are recorded from V3 (`9fb0290`). |

### `test_weather.py` (new)

| Test | Lines | Covers |
|---|---|---|
| `test_weather_points_and_state_are_validated` | 31–47 | valid boundary keyframes (−10, 50 °C; 0, 50 mm/h); 7 invalid keyframes; bad timelines; wetness −0.01, 1.01, NaN rejected; 0 and 1 accepted; initial `Conditions` and track temperature |
| `test_timeline_is_held_before_and_after_and_linear_between` | 50–58 | timeline interpolation |
| `test_rain_wets_the_track_gradually_up_to_a_balance_and_never_past_one` | 61–69 | evolution over time; no jumps (< 0.01 per 0.1 s at the heaviest rain); balance point |
| `test_track_dries_without_rain_faster_when_warmer_and_not_at_all_at_zero_degrees` | 72–82 | drying, temperature boundaries (0 °C, −10 °C), cold rain stays ≤ 1, dry stays dry |
| `test_wetness_costs_slicks_far_more_grip_than_wet_tyres` | 85–93 | dry against wet grip; wetness 0 equals V2 grip; wet tyre faster on a soaked track |
| `test_best_compound_changes_with_wetness_at_the_documented_crossovers` | 96–105 | relative suitability; just below and above both crossovers; dry-only table |
| `test_weather_aware_strategy_asks_for_the_right_tyres` | 108–115 | strategy reads the weather: inter, wet, back to soft, margin, planned stop first, fixed plans ignore weather |
| `test_rain_during_a_race_slows_slicks_and_a_weather_aware_car_switches` | 118–138 | weather change during a race: events in order, slicks much slower, pits to inter then wet, the reacting car wins |
| `test_lap_profiles_follow_wetness_within_one_step_of_resolution` | 141–150 | mid-lap profile refresh within `WETNESS_STEP` |
| `test_drying_track_logs_rain_free_change_back_to_slicks` | 153–157 | "best tyres" event on a drying track with no rain |
| `test_dry_weather_gives_the_same_race_as_no_weather` | 160–167 | a no-rain timeline is identical to `weather=None` (V3) |
| `test_weather_must_be_fresh_for_each_race` | 170–174 | a used `Weather` is rejected |

### `README.md` (modified)

Updated for V4: current version, weather configuration, how to reproduce V1–V3, a scripted weather race with its expected output, test commands, layout and doc links. The V2 list of impossible plans now says "a compound not in the race's table" instead of "wet tyres".

## Tests executed

All commands were run from the repository root on Python 3.12.3.

| Command | When | Result |
|---|---|---|
| All four existing test files | before V4 changes | `ok` |
| V3 3-car Stadium race | before V4 changes | values recorded in `test_v3_race_results_unchanged_without_weather` |
| `python3 test_simulation.py` | after V4 | `ok` (2 tests) |
| `python3 test_race.py` | after V4 | `ok` (12 tests) |
| `python3 test_tyres_fuel_pits.py` | after V4 | `ok` (13 tests) |
| `python3 test_traffic.py` | after V4 | `ok` (15 tests) |
| `python3 test_weather.py` | after V4 | `ok` (12 tests, about 1.4 s) |
| README weather example | after V4 | output exactly as shown in the README, about 3.6 s |
| `python3 main.py` | after V4 | unchanged: no weather in `main.py`, so it is V3's dry race |

**Mutation check (manual, not committed).** In a scratch copy, 17 deliberate bugs were introduced one at a time:

- no wetting;
- no drying floor;
- constant track temperature;
- wetness jumping straight to the balance point;
- no interpolation;
- no rain validation;
- equal timeline times accepted;
- no wet grip loss;
- the worst compound chosen as best;
- no weather margin;
- `react_to_weather` ignored;
- no mid-lap profile refresh;
- profiles ignoring wetness;
- no rain events;
- no "best tyres" events;
- a used weather accepted;
- weather never advanced.

The first run missed "no drying floor". A sub-zero rain case was added to the temperature-boundary test, and all 17 are now caught.

No test was skipped. pytest is not used.

## Commands

```bash
python3 main.py                  # V3-style dry race (unchanged)
python3 test_simulation.py
python3 test_race.py
python3 test_tyres_fuel_pits.py
python3 test_traffic.py
python3 test_weather.py
```

The README "Weather example" runs a race with a scripted weather timeline.

## Deliberately absent in V4

| Feature | Planned for |
|---|---|
| Race-control reactions to rain: safety car, DRS disabled, red flags | V5 |
| Calibrated wet grip, wetting and drying rates | V6 |
| Learned or optimised weather strategies | V7–V8 |
| Rain forecasting or uncertainty, a wetness that varies around the lap, spray, tyre temperatures and overheating, CFD | not planned |

## Known limitations

See IMPLEMENTATION.md §12. In short:

- one wetness for the whole track;
- rain has no effect on aerodynamics, DRS or dirty air;
- track temperature only drives drying;
- intermediates and wets do not overheat;
- the weather policy ignores laps remaining and can make a stop that does not pay off;
- grip can lag the track by up to 0.05 of wetness;
- all values are placeholders;
- `main.py` does not use weather; the README example does.
