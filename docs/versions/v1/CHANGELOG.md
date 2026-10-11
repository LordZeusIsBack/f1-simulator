# V1 changelog: multi-car race simulation

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V0 baseline) | `76f1562` "Added code for simulation testing" |
| V1 version commit | `3fbf3508bf42ac0523218977797e0505f9f4989c` (`3fbf350`) |
| Commit message | `feat(v1): add multi-car race simulation` |

**Note on the hash.** A Git commit's hash is computed from its contents, so a file cannot contain the hash of the commit it is in. If the hash were written in and the commit amended, the amended commit would get a new hash and the recorded one would point at a commit that was never pushed.

The hash is therefore recorded in a small follow-up commit, `docs(v1): record version commit hash in changelog`. That commit changes only this table. Both commits are pushed together. The hash in the table above is the version commit that contains all V1 code, tests and docs.

Line numbers below refer to the version commit and may shift in later versions.

## Files

| File | Status |
|---|---|
| `race.py` | **new** |
| `test_race.py` | **new** |
| `docs/versions/v1/IMPLEMENTATION.md`, `CODE_FLOW.md`, `CHANGELOG.md` | **new** |
| `simulation.py` | modified (refactor, no behaviour change) |
| `main.py` | modified (race added after the unchanged V0 output) |
| `test_simulation.py` | modified (one test added; existing test unchanged) |
| `README.md` | modified (was empty) |
| `abstract_classes.py`, `cars.py`, `physics.py`, `tracks.py`, `pyproject.toml`, `uv.lock` | **unchanged** |
| Removed files | none |

## Changes per file

### `race.py` (new, ~102 lines)

| Symbol | Lines | What it is |
|---|---|---|
| `GRID_SPACING` | 7 | 8.0 m between grid slots. Model assumption. |
| `RaceCar` (dataclass) | 10–17 | One car in one race. Fields: `number: int` (unique identifier), `team: str`, `car: Car` (shared configuration), `distance: float` (m from the start line, negative on the grid), `finish_time: float \| None` (s). |
| `LapProfile` | 20–39 | Converts the V0 speed profile into cumulative `distance`/`time` tables (5 901 entries on Monza). |
| `LapProfile.__init__` | 23–29 | Calls `simulate_lap` and `track_points`. Applies the trapezoid time formula per point. |
| `LapProfile.time_at(distance)` | 31–34 | Seconds from the start line to any distance, on any lap, including negative distances. |
| `LapProfile.distance_at(time)` | 36–39 | Inverse of `time_at`. |
| `_interpolate(x, xs, ys)` | 42–44 | Linear interpolation using `bisect_right`. |
| `Race` | 47–102 | Race state and orchestration. |
| `Race.__init__` | 50–65 | Validates inputs, builds one `LapProfile` per car, places cars on the grid. |
| `Race.finished` (property) | 67–69 | `True` when every car has a `finish_time`. |
| `Race.laps_completed(car)` | 71–74 | `floor(distance / L)`, at least 0; equals `laps` once finished. |
| `Race.step(dt)` | 76–90 | Advances every running car by `dt` s along its profile. Detects the finish and records the exact crossing time. Then advances `time`. |
| `Race.run(dt=0.5)` | 92–95 | Calls `step` until `finished`, returns `standings()`. |
| `Race.standings()` | 97–102 | Finished cars by `finish_time`, then running cars by `distance`. Ties keep grid order. |

**Why:** V0 had no notion of a race, of more than one car at a time, or of state that changes during a race. The prompt asks for these, with configuration kept separate from state.

### `simulation.py` (modified)

| Symbol | Lines | Before | After |
|---|---|---|---|
| `track_points(track)` | 8–14 | Did not exist. The same loop was inline in `simulate_lap`. | New function returning `[(ds, radius, gradient), ...]`. |
| `simulate_lap(car, track)` | 17–37 | Built `points` inline. | Calls `track_points(track)`. Signature, return value and results are unchanged. |
| `STEP` | 5 | unchanged | unchanged |

**Why:** `LapProfile` needs each point's `ds` to map V0 speeds to distances. Alternatives and their drawbacks are in IMPLEMENTATION.md section 5.

### `main.py` (modified)

| Symbol | Lines | Change |
|---|---|---|
| `import sys`, `from race import ...` | 1, 4 | new imports |
| `CARS_PER_TEAM = 2` | 8 | new: each team fields two cars |
| `RACE_LAPS = 53` | 9 | new: default race length, Monza's Grand Prix distance |
| `DT = 0.5` | 10 | new: race step in seconds |
| `print_standings(race, title)` | 13–24 | new: prints position, `#number`, team, laps, gap (m while running, s once finished) |
| `main()` V0 block | 28–37 | **unchanged**: still prints the flying-lap table |
| `main()` race block | 39–48 | new: reads optional laps argument, builds the 8-car grid from `CARS`, runs the race, prints standings after lap 1 and the final classification |

### `test_simulation.py` (modified)

| Symbol | Lines | Change |
|---|---|---|
| imports | 3–7 | added `CARS` and `Monza` |
| `test_car_brakes_down_to_grip_limit` | 15–19 | **unchanged** |
| `test_monza_lap_times_unchanged_from_v0` | 22–27 | new: compares all four Monza lap times with values recorded at `76f1562` (relative tolerance 10⁻¹²). This is a regression guard, not a validation against real F1. |
| `__main__` | 30–33 | also runs the new test |

### `test_race.py` (new)

| Test | Lines | Covers |
|---|---|---|
| `test_grid_puts_cars_behind_the_line_in_given_order` | 18–24 | Race initialisation, grid distances 0/−8/−16 m, time 0, standings = grid, 0 laps |
| `test_team_mates_share_the_car_but_not_the_race_state` | 27–36 | Same `Car` object, independent `distance` |
| `test_positions_follow_progress_not_grid_order` | 39–45 | A faster car starting behind ends ahead |
| `test_running_cars_are_ordered_by_distance_and_finished_cars_lead` | 48–54 | Sort rules for running and finished cars |
| `test_single_car_race_lasts_laps_times_the_v0_lap_time` | 57–63 | One participant; finish time = laps × V0 lap time; distance clamped |
| `test_lap_is_counted_when_the_car_crosses_the_line` | 66–72 | Lap counter changes exactly at the line |
| `test_race_ends_only_when_every_car_has_completed_all_laps` | 75–83 | Multiple participants; completion condition |
| `test_results_do_not_depend_on_step_size` | 86–92 | `dt = 3.0` and `dt = 0.05` give the same finish times (±10⁻⁶ s) |
| `test_same_inputs_give_identical_results` | 95–100 | Determinism (exact equality) |
| `test_lap_profile_reproduces_the_v0_lap_and_inverts` | 103–108 | Profile lap time and length match V0; `distance_at(time_at(d)) ≈ d` (±10⁻⁹ m) |
| `test_invalid_race_configuration_is_rejected` | 111–122 | `laps` of 0, −1, 2.5, "3"; empty grid; duplicate numbers; `dt` of 0 or −0.5 |
| `__main__` runner | 125–129 | Runs every `test_*` function without third-party tools |

The test track is the small `Stadium` already defined in `test_simulation.py`: two 500 m straights and two 50 m-radius half circles. Tests use it for speed. `assert_raises` is `unittest.TestCase().assertRaises` from the standard library.

### `README.md` (modified)

It was empty. It now has a project description, the current version, setup, run and test commands, the file layout, and links to these docs.

## Tests executed

All commands were run from the repository root on Python 3.12.3.

| Command | When | Result |
|---|---|---|
| `python3 test_simulation.py` | before any change (V0) | `ok` (1 test) |
| `python3 main.py` | before any change (V0) | Lap times 1:34.555 / 1:35.196 / 1:33.998 / 1:35.291 |
| `python3 test_simulation.py` | after V1 | `ok` (2 tests) |
| `python3 test_race.py` | after V1 | `ok` (11 tests) |
| `uv run --offline test_race.py` | after V1 | `ok` |
| `python3 main.py` | after V1 | V0 table identical to before. 53-lap race finishes: McLaren #5 first in 4 982.461 s; Mercedes #8 last, +69.003 s. Runtime ≈ 0.6 s. |
| `python3 main.py 1` | after V1 | 1-lap race, McLaren #5 wins in 94.547 s |

**Mutation check (manual, not committed).** In a scratch copy, the race logic was deliberately broken six ways:

- finish time taken as the end of the step;
- standings sorted in reverse;
- all cars put on the same grid spot;
- `laps = 0` accepted;
- finished cars reporting 0 laps;
- finished cars still moving.

`test_race.py` failed for every one.

pytest is not installed, and none of these tests used it. No tests were skipped.

## Commands

```bash
python3 main.py            # V0 lap table + 53-lap race
python3 main.py 5          # 5-lap race
python3 test_simulation.py
python3 test_race.py
uv run main.py             # same, through uv
```

## Deliberately absent in V1

| Feature | Planned for |
|---|---|
| Tyre compounds and wear, fuel load and burn, pit stops, strategy | V2 |
| Car-to-car interaction: blocking, overtaking rules, DRS, driver attributes | V3 |
| Weather, track wetness | V4 |
| Chequered-flag rule for lapped cars, flags, safety car, VSC, retirements, penalties | V5 |
| Calibration against real data | V6 |
| RL environment | V7 |
| Qualifying | not on the roadmap; the grid is the input list order |
| Standing start (accelerating from 0 m/s) | not on the roadmap; cars start at their flying-lap speed |

## Known limitations

- Every lap, including lap 1, repeats the V0 flying lap. This is effectively a rolling start.
- Cars pass through each other. Positions change only through pace differences.
- Every car runs the full lap count; lapped cars are not flagged early.
- `Race` resets the `RaceCar`s it receives, so they cannot be reused across races.
- `main.py`'s "After lap 1" snapshot happens at a step boundary, so its race time is a multiple of `DT`. Finish times are exact.
- Car numbers 1–8 are identifiers only, not real F1 numbers.
- Physics, car parameters and track geometry are V0 placeholders. Simulated laps are about 15 s slower than real Monza qualifying laps.
- `Car` is still a thin wrapper around `CarSpecification`. Left as is to avoid an unrequested refactor.
- `TyreCompound` remains defined but unused, as in V0.
