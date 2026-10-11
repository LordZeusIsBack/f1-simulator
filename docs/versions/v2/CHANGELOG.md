# V2 changelog: tyres, fuel and pit strategy

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V1) | `0794850` "docs(v1): record version commit hash in changelog" (V1 code is in `3fbf350`) |
| V2 version commit | `908961f69e2bdd79507419a91015f3982563991e` (`908961f`) |
| Commit message | `feat(v2): add tyres, fuel and pit strategy` |

As in V1, a commit cannot contain its own hash. The hash is therefore filled in by a follow-up commit, `docs(v2): record version commit hash in changelog`, which changes only this table.

Line numbers refer to the V2 version commit and may shift in later versions.

## Files

| File | Origin | V2 status |
|---|---|---|
| `tyres.py` | — | **new** |
| `strategy.py` | — | **new** |
| `test_tyres_fuel_pits.py` | — | **new** |
| `docs/versions/v2/*.md` | — | **new** |
| `race.py` | V1 | modified |
| `main.py` | V0, extended in V1 | modified |
| `test_race.py` | V1 | modified (all V1 assertions kept) |
| `README.md` | V1 | modified |
| `physics.py` | V0 | modified (new optional parameter, no behaviour change) |
| `simulation.py` | V0, refactored in V1 | modified (new optional parameter, no behaviour change) |
| `abstract_classes.py` | V0 | **unchanged**. `TyreCompound` is now used. |
| `cars.py`, `tracks.py`, `test_simulation.py`, `pyproject.toml`, `uv.lock`, `docs/versions/v1/*` | | **unchanged** |
| Removed files | | none |

## Inherited and new functionality

| Inherited (unchanged in behaviour) | New in V2 |
|---|---|
| V0 physics and `simulate_lap` at μ = 1.8, mass from the spec | `tyre_grip` input; mass + fuel |
| V1 grid, positions, exact line-crossing times, `dt` independence, standings | A profile rebuilt every lap from fuel and tyre state |
| V1 finish rule (every car completes all laps) | Pit stops, pit-event log |
| V1 `LapProfile` distance/time lookup | `LapProfile` for any grip and fuel; `lap_profile` cache |
| | Tyre compounds, wear, grip; fuel burn; strategies; plan validation |

## Changes per file

### `tyres.py` (new, 35 lines)

| Symbol | Lines | Purpose |
|---|---|---|
| `WORN_GRIP_LOSS` | 7 | 0.06: fraction of grip lost at full wear (placeholder) |
| `Compound(NamedTuple)` | 10–12 | `grip` (μ of a new tyre), `wear_per_lap` |
| `COMPOUNDS` | 17–21 | SOFT 1.83 / 0.05, MEDIUM `TYRE_GRIP` (1.8) / 0.03, HARD 1.775 / 0.02. No wet compounds. |
| `Tyres` (frozen dataclass) | 24–35 | `compound`, `laps`; `wear()` = min(1, laps × rate); `grip()` = μ₀ × (1 − 0.06 × wear) |

### `strategy.py` (new, 23 lines)

| Symbol | Lines | Purpose |
|---|---|---|
| `PitStop` (frozen) | 6–11 | `lap` (stop as this lap is completed), `compound` (None keeps the tyres), `fuel` (kg added) |
| `Strategy` (frozen) | 14–23 | `compound`, `fuel` (start, kg), `stops`, `name`; `stop_after(lap)` |

### `race.py` (modified, 102 → 225 lines)

| Symbol | Lines | Before (V1) | After (V2) |
|---|---|---|---|
| imports | 1–9 | — | adds `replace`, `lru_cache`, `TyreCompound`, `TYRE_GRIP`, strategy and tyre types |
| `PIT_LOSS`, `FUEL_PER_LAP`, `FUEL_CAPACITY`, `REFUEL_RATE`, `FUEL_TOLERANCE` | 12–16 | — | new constants: 22 s, 1.9 kg/lap, 110 kg, 10 kg/s, 10⁻⁹ kg |
| `RaceCar` | 19–31 | number, team, car, distance, finish_time | adds `strategy` (input, default `None`), `laps`, `fuel`, `tyres`, `pit_exit` (state) |
| `PitEvent` | 34–42 | — | new frozen record of one stop |
| `LapProfile.__init__` | 48–55 | `(car, track)` | `(car, track, tyre_grip=TYRE_GRIP, fuel=0.0)`. Simulates with mass + fuel and the given grip. The defaults give V1's profile. |
| `time_at`, `distance_at`, `_interpolate` | 57–65, 75–77 | | unchanged |
| `lap_profile()` | 67–72 | — | new: `lru_cache(maxsize=16)` around `LapProfile` (marked `ponytail:`) |
| `Race.__init__` | 83–122 | track, laps, grid | adds keyword settings `pit_loss`, `fuel_per_lap`, `compounds`, plus `pit_events`, `_strategies` and the default strategy. Resets the V2 car state. |
| `Race._check` | 124–154 | — | new: pit and fuel rules, `ValueError` per car |
| `Race._profile` | 156–157 | — | new: current state → `lap_profile(...)` |
| `Race.laps_completed` | 163–164 | `floor(distance / L)`, or `laps` once finished | returns the stored `car.laps` |
| `Race.step` | 166–172 | advanced each car with one repeating profile | delegates to `_advance` |
| `Race._advance` | 174–192 | — | new: lap-by-lap progress, waits in the pits, exact crossings |
| `Race._complete_lap` | 194–205 | — | new: burns fuel, ages tyres, finishes or consults the strategy, rebuilds the profile |
| `Race._pit` | 207–213 | — | new: duration, `PitEvent`, tyre and fuel change, `pit_exit` |
| `Race.finished`, `run`, `standings` | 159–161, 215–225 | | unchanged |

**Why:** the profile must change lap by lap. V1's "one profile, divmod over total distance" approach could not do that. Stored lap counts avoid floating-point off-by-one errors at the line.

### `physics.py` (modified)

| Function | Change |
|---|---|
| `corner_speed` | new parameter `tyre_grip: float = TYRE_GRIP`, used in place of the constant |
| `longitudinal_grip` | same |
| `acceleration`, `deceleration` | same, passed on to `longitudinal_grip` |

### `simulation.py` (modified)

| Symbol | Change |
|---|---|
| import | adds `TYRE_GRIP` |
| `simulate_lap(car, track, tyre_grip=TYRE_GRIP)` | lines 17–37: new parameter, passed to `corner_speed`, `acceleration` and `deceleration`. Return value unchanged. |

**Why** (`physics.py` and `simulation.py`): grip must vary per lap without a global variable. See IMPLEMENTATION.md §6.1.

### `main.py` (modified)

| Symbol | Lines | Change |
|---|---|---|
| `CARS_PER_TEAM` | — | **removed**. The number of cars per team now equals the number of plans (2). |
| `strategies(laps)` | 14–20 | new: "no stop (M)" and "1 stop (M-H)" with a stop after `laps // 2` |
| `print_standings` | 23–37 | adds a strategy-name column |
| `print_pit_stops` | 40–48 | new: one line per `PitEvent` |
| `main()` | 51–74 | V0 block unchanged. Grid: one car per team per plan. Prints the pit log. `main.py 1` is now rejected, because no stop fits in one lap. |

### `test_race.py` (modified)

| Change | Lines | Why |
|---|---|---|
| imports, `V1_TYRES`, `v1_race()` | 1–25 | `v1_race` builds a `Race` with fuel burn and wear switched off. That is how V1 behaviour is expressed in V2. |
| `Race(Stadium()` → `v1_race(Stadium()` in every V1 test | 39–143 | The V1 assertions (exact V0 lap times, `dt` independence and so on) describe the no-fuel, no-wear case. No assertion was changed or removed. |
| `test_v1_monza_race_results_unchanged` | 28–36 | new regression test: 53-lap, 8-car Monza finish times recorded from V1 (`3fbf350`), tolerance 10⁻⁶ s |

### `test_tyres_fuel_pits.py` (new)

| Test | Lines | Covers |
|---|---|---|
| `test_dry_compounds_start_new_and_wet_ones_are_rejected` | 25–35 | valid compounds; new-set state; MEDIUM equals V0 grip; INTERMEDIATE, WET and `"soft"` rejected |
| `test_wear_grows_per_lap_and_costs_grip_and_lap_time` | 38–47 | wear = laps × rate; capped at 1; grip strictly falls, then holds; worn lap slower |
| `test_new_softer_tyres_are_faster` | 50–53 | soft < medium < hard lap time; medium = V0 |
| `test_fuel_burns_every_lap_and_its_mass_slows_the_car` | 56–65 | fuel 10 → 8 → 6 → 4 → 2 kg by lap; 100 kg slower than 0 kg |
| `test_pit_stop_costs_pit_loss_and_fits_new_tyres` | 68–77 | with no wear, a stop costs exactly `pit_loss`; event fields; tyre laps reset |
| `test_car_stands_still_in_the_pits` | 80–88 | distance frozen at the line until `pit_exit`, then moves on new tyres |
| `test_refuelling_adds_fuel_and_stationary_time` | 91–96 | duration = pit loss + fuel / rate; fuel-only stop keeps the tyres |
| `test_impossible_pit_plans_are_rejected` | 99–120 | 13 impossible plans; negative `pit_loss` or `fuel_per_lap` |
| `test_strategy_is_followed_across_the_race` | 123–132 | two-stop plan: event laps, tyres, final fuel and tyres, event order |
| `test_default_plan_is_no_stop_on_mediums_with_just_enough_fuel` | 135–138 | `strategy=None` behaviour |
| `test_which_strategy_wins_depends_on_wear_and_pit_loss` | 141–151 | no wear: no-stop wins; heavy wear and cheap stop: one-stop wins |
| `test_results_with_stops_are_deterministic_and_independent_of_step_size` | 154–165 | identical reruns; `dt` 3.0 vs 0.05 s, including stop times |

The tests use V1's `Stadium` track, `FAST` car and `lap_time` helper, so they run in under a second.

### `README.md` (modified)

Updated for V2: current version, configuration options, the strategy-comparison example, test commands and documentation links.

## Tests executed

All commands were run from the repository root on Python 3.12.3.

| Command | When | Result |
|---|---|---|
| `python3 test_simulation.py` | before V2 changes | `ok` |
| `python3 test_race.py` | before V2 changes | `ok` |
| V1 53-lap Monza run (to record regression values) | before V2 changes | recorded in `test_v1_monza_race_results_unchanged` |
| `python3 test_simulation.py` | after V2 | `ok` (2 tests) |
| `python3 test_race.py` | after V2 | `ok` (12 tests, about 0.8 s) |
| `python3 test_tyres_fuel_pits.py` | after V2 | `ok` (12 tests, about 0.6 s) |
| `python3 main.py` | after V2 | V0 table unchanged. Within each team, "1 stop (M-H)" beats "no stop (M)" by 5.7–6.2 s. Winner #6 McLaren in 5111.063 s. 4 pit events. About 10.7 s runtime. |
| README strategy-comparison snippet | after V2 | 5124.340 / 5116.691 / 5110.338 / 5104.174 / 5087.915 s (no stop H / no stop M / 1 stop M-H / 2 stops S-M-S / 1 stop + refuel). About 8.5 s. |

**Mutation check (manual, not committed).** In a scratch copy, 15 deliberate bugs were introduced one at a time:

- fuel not burned;
- tyres not aged;
- refuel time ignored;
- car not held in the pits;
- fuel mass ignored;
- tyre grip ignored;
- strategy ignored;
- stop allowed on the final lap;
- tank overflow allowed;
- running dry allowed;
- profile not rebuilt each lap;
- fuel not added at the stop;
- wear not capped;
- wear not affecting grip;
- "no-change" stop allowed.

The test suite failed for every one.

No test was skipped. pytest is not installed and was not used.

## Commands

```bash
python3 main.py              # V0 table + 53-lap race, two plans per team
python3 main.py 10           # 10-lap race (needs at least 2 laps for the one-stop plan)
python3 test_simulation.py
python3 test_race.py
python3 test_tyres_fuel_pits.py
```

## Deliberately absent in V2

| Feature | Planned for |
|---|---|
| Overtaking, traffic, undercut/overcut effects, DRS, driver attributes | V3 |
| Wet and intermediate tyres, weather, track evolution | V4 |
| Mandatory two-compound rule, penalties, safety car (cheap stops), retirements and running dry | V5 |
| Real tyre/fuel calibration | V6 |
| Strategy search or optimisation, reactive or learned policies | V7–V8 |
| Tyre temperature, cliff and punctures | not planned yet |

## Known limitations

- All tyre, fuel and pit numbers are placeholders.
- Mass and grip change once per lap, at the line.
- The pit box is at the start/finish line, and refuelling time is added to the stop rather than overlapping the tyre change.
- `lap_profile` caches by object identity.
- `python3 main.py` takes about 11 s, because one physics lap is computed per car per lap.
- `main.py 1` is rejected, because the one-stop plan cannot fit into one lap.
- `race.pit_events` is in processing order, which is not strictly time order when two cars stop in the same step.
- V1 limitations still apply: rolling start, no interaction between cars, every car runs the full distance.
