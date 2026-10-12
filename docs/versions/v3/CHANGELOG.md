# V3 changelog: traffic, overtaking, DRS and driver attributes

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V2) | `97f759d` "docs(v2): record version commit hash in changelog" (V2 code is in `908961f`) |
| V3 version commit | `PENDING` |
| Commit message | `feat(v3): add traffic, overtaking, DRS and driver attributes` |

As in V1 and V2, the hash is recorded by a follow-up commit, `docs(v3): record version commit hash in changelog`, which changes only this table.

Line numbers refer to the V3 version commit and may shift later.

## How V3 differs from V2

| V2 | V3 |
|---|---|
| Cars ignore each other and drive through one another | Cars interact: dirty air, DRS, held up behind a car unless an overtaking rule is met |
| Pace comes from the car, tyres and fuel | Plus the driver's `pace`, dirty air and DRS (a time factor) |
| Results are independent of `dt` | With traffic, decisions are made per step, so results depend on `dt` (`main.py` uses 0.1 s) |
| Cars processed in grid order | With traffic, processed in race order (leader first) |
| Event log: `pit_events` | Plus `overtakes` ("passed", "aborted", "held up") |
| — | `Race(traffic=None)` reproduces V2 exactly |

## Files

| File | Origin | V3 status |
|---|---|---|
| `drivers.py` | — | **new** |
| `traffic.py` | — | **new** |
| `test_traffic.py` | — | **new** |
| `docs/versions/v3/*.md` | — | **new** |
| `race.py` | V1, V2 | modified |
| `main.py` | V0–V2 | modified |
| `test_race.py` | V1, V2 | modified (V1 helper turns traffic off) |
| `test_tyres_fuel_pits.py` | V2 | modified (one test turns traffic off; V2 regression test added) |
| `README.md` | V1, V2 | modified |
| `abstract_classes.py`, `cars.py`, `tracks.py`, `physics.py`, `simulation.py`, `tyres.py`, `strategy.py`, `test_simulation.py`, `pyproject.toml`, `uv.lock`, `docs/versions/v1/*`, `docs/versions/v2/*` | | **unchanged** |
| Removed files | | none |

## Changes per file

### `drivers.py` (new, 21 lines)

| Symbol | Lines | Behaviour |
|---|---|---|
| `PACE_SPREAD` | 3 | 0.01: lap-time fraction lost by a pace-0 driver (placeholder) |
| `Driver` (frozen dataclass) | 6–21 | `name`, `pace` (default 1.0), `racecraft` (default 0.5) |
| `Driver.__post_init__` | 13–17 | `ValueError` unless each attribute is a real number in [0, 1] (rejects bool, str, None, NaN) |
| `Driver.time_factor()` | 19–21 | `1 + PACE_SPREAD × (1 − pace)` |

### `traffic.py` (new, 52 lines)

| Symbol | Lines | Behaviour |
|---|---|---|
| `TrafficRules` (frozen) | 8–19 | `min_gap` 5 m, `dirty_air_interval` 1.0 s, `dirty_air_loss` 0.02, `drs_interval` 1.0 s, `drs_from_lap` 3, `drs_min_straight` 500 m, `drs_gain` 0.035, `overtake_margin` 2.0 m/s, `racecraft_effect` 1.0 m/s |
| `is_straight(segment)` | 22–23 | radius is infinite |
| `is_drs_zone(rules, segment)` | 26–27 | straight and length ≥ `drs_min_straight` |
| `time_factor(rules, driver, segment, interval, drs)` | 30–37 | driver factor × dirty air (corner and interval < 1.0) × DRS (zone and `drs`) |
| `drs_enabled(rules, lap, interval)` | 40–42 | `lap ≥ 3` and `interval < 1.0` |
| `required_advantage(rules, attacker, defender)` | 45–47 | `2.0 − 1.0 × (attacker.racecraft − defender.racecraft)` m/s |
| `can_attack(rules, segment, advantage, attacker, defender)` | 50–52 | straight and `advantage ≥ required` |

### `race.py` (modified, 225 → 334 lines)

| Symbol | Lines | Before (V2) | After (V3) |
|---|---|---|---|
| imports | 1–13 | | adds `math`, `accumulate`, `TrackSegment`, `Driver` and the `traffic` functions |
| `RaceCar` | 23–39 | V2 fields | adds `driver` (input), and `drs`, `attack`, `held_by` (state) |
| `OvertakeEvent` | 42–51 | — | new: `time`, `lap`, `attacker`, `defender`, `outcome`, `advantage`, `required`, `drs` |
| `LapProfile.__init__` | 68–76 | distance/time tables | also keeps `speed` (m/s per table entry) |
| `LapProfile.speed_at` | 88–90 | — | new: speed at any distance |
| `Race.__init__` | 108–152 | V2 settings | adds `traffic=TrafficRules()` (None = V2), `overtakes`, `_segment_starts`; resets `drs`, `attack`, `held_by` |
| `Race.step` | 196–207 | each car `_advance` in grid order | with traffic: race order; on-track cars go through `_drive`; others `_advance` with the driver factor |
| `Race._drive` | 209–243 | — | new: car ahead, interval, time factor, pass decision, move, pass/abort, DRS detection |
| `Race._advance` | 245–270 | `(car, end)` | `(car, end, factor=1.0, limit=None)`: profile time stretched by `factor`; stops at `limit` |
| `Race._next_line` | 272–274 | inline in `_advance` | extracted, same formula |
| `Race._on_track` | 276–277 | — | not finished and not in the pits |
| `Race._segment` | 279–280 | — | segment at the car's lap position |
| `Race._free_distance` | 282–286 | — | where the car would get to by `end` unobstructed |
| `Race._speed` | 288–290 | — | profile speed at a distance ÷ factor |
| `Race.car_ahead` | 292–295 | — | **public**: nearest on-track car ahead in race order |
| `Race.interval` | 297–301 | — | **public**: follower's time to the car ahead's position |
| `_check`, `_profile`, `_complete_lap`, `_pit`, `run`, `standings`, `laps_completed`, `finished` | | | unchanged |

**Why:** interactions need race order, a notion of "car ahead", and a way to slow, speed up or stop a car within a step. Everything else (fuel, tyres, stops, exact line crossings) still runs through the V2 code inside `_advance`.

### `main.py` (modified)

| Symbol | Lines | Change |
|---|---|---|
| `DT` | 11 | 0.5 → **0.1 s**, because traffic decisions are made once per step |
| `print_overtakes(race)` | 51–59 | new: count of passes and of held-up events, then one line per pass |
| `main()` | 62–86 | calls `print_overtakes`. Race setup is unchanged, so traffic is on by default. |

### `test_race.py` (modified)

| Change | Lines | Why |
|---|---|---|
| `v1_race(...)` passes `traffic=None` | 19–21 | V1 had no interactions. All V1 assertions are unchanged. |

### `test_tyres_fuel_pits.py` (modified)

| Change | Lines | Why |
|---|---|---|
| imports `SLOW` | 8 | used by the new regression test |
| `test_results_with_stops_are_deterministic_and_independent_of_step_size` uses `traffic=None` | 154–165 | It checks V2's `dt` independence, which holds only without interactions. |
| `test_v2_race_results_unchanged_without_traffic` | 169–180 | new: a 4-car, 8-lap race with stops on the Stadium track. Finish times and pit events recorded from V2 (`908961f`), tolerance 10⁻⁶ s. |

### `test_traffic.py` (new)

| Test | Lines | Covers |
|---|---|---|
| `test_driver_attributes_are_validated` | 33–41 | defaults, time factor, 6 invalid values × 2 attributes |
| `test_driver_pace_stretches_lap_time_with_or_without_traffic` | 45–49 | pace 0 gives exactly 1.01 × lap time, with traffic on and off |
| `test_car_ahead_is_the_nearest_car_on_track` | 52–59 | nearest car; cars in the pits and finished cars skipped; leader has none |
| `test_interval_is_the_followers_time_to_the_car_ahead` | 62–68 | 8 m ≈ 8 / v; one lap further = + one lap time |
| `test_dirty_air_only_close_behind_and_only_in_corners` | 71–76 | inside the range (0.99 s), at and outside it (1.0, 5.0 s); straight |
| `test_follower_loses_time_in_traffic_and_the_leader_does_not` | 79–87 | race-level dirty-air effect; the leader is unaffected |
| `test_drs_thresholds` | 90–97 | 0.999 s on, 1.0 s off, 1.5 s off, lap 2 off; zone ≥ 500 m only; corner none |
| `test_drs_follows_the_rule_at_every_line_crossing` | 100–116 | every crossing matches the rule; on (lap 3), off before lap 3, off when the car ahead pits |
| `test_faster_car_passes_on_a_straight_and_positions_update` | 119–124 | successful pass, `advantage ≥ required`, standings flip |
| `test_small_advantage_is_held_up_without_drs_and_passes_with_it` | 127–139 | unsuccessful attempts, never closer than `min_gap` while held, DRS enables the pass |
| `test_racecraft_decides_a_close_fight` | 142–155 | required margin per racecraft; no attack in a corner; same cars, racecraft flips the outcome |
| `test_passing_a_car_in_the_pits_is_not_an_overtake` | 158–165 | pit interaction: position changes, no overtake event |
| `test_tyre_grip_feeds_the_overtaking_decision` | 168–176 | tyre state (grip) decides whether a pass happens |
| `test_traffic_race_is_deterministic` | 179–188 | identical replay of times, overtakes and pit events |

### `README.md` (modified)

Updated for V3: current version, traffic configuration, a 3-car traffic scenario with its expected output, test commands and doc links.

## Tests executed

All commands were run from the repository root on Python 3.12.3.

| Command | When | Result |
|---|---|---|
| `python3 test_simulation.py`, `test_race.py`, `test_tyres_fuel_pits.py` | before V3 changes | `ok` |
| V2 4-car Stadium race | before V3 changes | values recorded in `test_v2_race_results_unchanged_without_traffic` |
| `python3 test_simulation.py` | after V3 | `ok` (2 tests) |
| `python3 test_race.py` | after V3 | `ok` (12 tests) |
| `python3 test_tyres_fuel_pits.py` | after V3 | `ok` (13 tests) |
| `python3 test_traffic.py` | after V3 | `ok` (14 tests, about 1.2 s) |
| `python3 main.py` | after V3 | runs in about 19 s. 17 passes, 372 held-up events. Winner #6 McLaren (1 stop) in 5124.716 s. |
| README traffic scenario | after V3 | output as shown in the README, about 1.3 s |
| The 53-lap race at `dt` = 0.5, 0.25, 0.1 and 0.05 s | manual | results depend on `dt` (IMPLEMENTATION.md §12) |

**Mutation check (manual, not committed).** In a scratch copy, 16 deliberate bugs were introduced one at a time:

- dirty air also on straights;
- dirty air never applied;
- DRS outside zones;
- DRS from lap 1;
- DRS at exactly 1.0 s;
- passing in corners;
- racecraft ignored;
- no holding behind;
- attacks never started;
- defender speed ignored;
- cars in the pits treated as on track;
- passes not logged;
- DRS kept in the pits;
- driver pace ignored;
- driver validation removed;
- driver pace ignored without traffic.

The first run missed the last one. `test_driver_pace_stretches_lap_time_with_or_without_traffic` was added, and all 16 are now caught.

No test was skipped. pytest is not used.

## Commands

```bash
python3 main.py                  # 53-lap Monza race with traffic (≈ 19 s)
python3 test_simulation.py
python3 test_race.py
python3 test_tyres_fuel_pits.py
python3 test_traffic.py
```

## Deliberately absent in V3

| Feature | Planned for |
|---|---|
| Wet weather, track wetness | V4 |
| Blue flags and lapped-car interaction, safety car, incidents, contact, penalties | V5 |
| Calibrated dirty-air, DRS and overtaking values | V6 |
| Learned or optimised driving and strategy | V7–V8 |
| Driver consistency (would need seeded randomness), tyre management | not planned yet |
| Lateral position, side-by-side cornering, defensive lines | not planned |

## Known limitations

See IMPLEMENTATION.md §15. In short:

- the track is one-dimensional;
- lapped cars are ghosts;
- defenders do not defend;
- held cars wait at a fixed point within a step;
- at most one pass per car per step;
- results depend on `dt` and are sensitive near thresholds;
- identical cars can ping-pong with DRS;
- the held-up count has hysteresis;
- `car_ahead` cost grows with the square of the number of cars;
- all values are placeholders.
