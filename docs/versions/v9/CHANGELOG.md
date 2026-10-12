# V9 changelog: real circuits, richer track geometry, randomised race conditions

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V8) | `7bfd66a` "docs(v8): record version commit hash in changelog" |
| V9 version commit | `441b36edc481084c8eb27c03a05ad0b20b4dabc3` (`441b36e`) |
| Commit message | `feat(v9): add real circuits, new segment types and hidden race conditions` |

As in earlier versions, the hash is recorded by a follow-up commit, `docs(v9): record version commit hash in changelog`, which changes only this table.

## How V9 differs from V8

- **Simulator:**
  - new segment types (`Hairpin`, `Spiral`, `Chicane`, `Esses`) and banking for any segment;
  - 28 approximate real circuits;
  - the old Monza is kept as `MonzaV0`.

  With zero banking the physics is bit-identical to V0, and every V0–V5 regression test passes unchanged against `MonzaV0`.
- **Validation:**
  - recalibrated on the new Monza;
  - the report gains an all-circuits sanity check.
- **RL:**
  - the environment uses the calibrated grip, any circuit, and hidden random pit loss, fuel burn and tyre wear;
  - the V7 and V8 experiments were re-run.
- **Licensing:** a separate licence notice for the timing data, a `NOTICE` file, and credits.

No dependencies added. Simulator defaults (`TYRE_GRIP`, `PIT_LOSS`, `FUEL_PER_LAP`) are unchanged.

## 1. Code implementation

| File | Status | Change |
|---|---|---|
| `abstract_classes.py` | modified | `TrackSegment.banking` (default 0) and `points(step)`; new `Hairpin`, `Spiral`, `Chicane`, `Esses` |
| `physics.py` | modified | `banking` parameter on `corner_speed`, `longitudinal_grip`, `acceleration`, `deceleration` (`_tilt` gives exactly (1, 0) when flat) |
| `simulation.py` | modified | `track_points` = segments' own points; `simulate_lap` passes banking |
| `race.py` | modified | `LapProfile` unpacks 4-value points; new constant `FUEL_PER_KM` = 0.32 |
| `tracks.py` | rewritten (1,061 lines) | `MonzaV0` (old layout, unchanged); `LATERAL_G`, `radius_for`; builders; `Circuit` base; 28 circuits; `CIRCUITS` |
| `validation/model.py` | modified | `flying_laps(..., track=None)` |
| `validation/evaluate.py` | modified | `circuits()` and a report section for every circuit vs its lap record |
| `validation/config/calibrated.json` | regenerated | `tyre_grip` 2.9358 → 2.4811 (pit loss unchanged, 25.62) |
| `validation/reports/validation_report.md` | regenerated | New Monza numbers plus the 28-circuit table |
| `rl/env.py` | modified | `track`, `calibration`, hidden pit loss, fuel burn and tyre wear; circuit defaults for laps and chances; fuel for the worst case |
| `rl/experiment.py` | modified | Report text describes the new defaults |
| `rl/reports/experiment_report.md` | regenerated | V7 experiment re-run |
| `research/config.py` | modified | `env` = `{team, track}`, both validated |
| `research/scenario_coverage.py` | modified | Main evaluation with hidden pit loss; the report labels the pit-loss setting |
| `research/configs/*.json` | modified | `env.track`; sensitivity pit loss 22.0 (the old placeholder) |
| `research/results/scenario_coverage.{json,md}` | regenerated | V8 experiment re-run on the V9 code |
| `main.py` | modified | `python3 main.py [laps] [track]`; fuel per lap from the circuit length |
| `test_tracks.py` | **new** | 6 tests (below) |
| `test_rl.py` | modified | 3 new tests; construction cases for track, tank size and calibration; one stale comment fixed |
| `test_simulation.py`, `test_race.py` | modified | Regression tests use `MonzaV0` (their values were recorded on that layout) |
| `test_research.py` | modified | Tiny config uses `track`; 3 new invalid-config cases |
| `NOTICE`, `data/reference/LICENSE.md` | **new** | Licences and credits |
| `data/reference/README.md`, `README.md` | modified | Licence links; V9 sections; README examples pinned to `MonzaV0` |
| `docs/versions/v9/*` | **new** | This documentation |

Nothing was removed. The simulator constants `TYRE_GRIP`, `PIT_LOSS` and `FUEL_PER_LAP` are unchanged.

## 2. Successful execution

| Run | Outcome |
|---|---|
| `python3 -m validation.calibrate` | `tyre_grip` 2.4811, `pit_loss` 25.62 s |
| `python3 -m validation.evaluate` | Report regenerated (about 17 s) |
| `python3 -m research.scenario_coverage research/configs/smoke.json` | Complete in 21 s (pipeline check, output discarded) |
| `python3 -m rl.experiment` | Complete; report committed |
| `python3 -m research.scenario_coverage` | Complete: 0 failed episodes, 2,294.8 s (7 processes, sharing the CPU with the V7 re-run), code digest `88b54f1a…` |
| `python3 main.py`, `python3 main.py 5 Baku`, `python3 main.py 3 Nowhere` | Run (20.8 s for the full Monza race). An unknown track exits with the list of names. |
| README examples (V2–V5, on `MonzaV0`) | All 4 print exactly their documented output; the V7 example prints the new documented value |

Results are summarised in [IMPLEMENTATION.md §8](IMPLEMENTATION.md#8-results).

## Tests executed

New tests:

| Test | Covers |
|---|---|
| `test_hairpin_spiral_and_chicane_geometry` | Hairpin length; spiral curvature linear, monotonic, transition from a straight; chicane composition, radius, gradient; a chicane needs 2 parts |
| `test_plain_segments_cut_into_points_as_in_v0` | The V0 point cut, including a segment shorter than one step |
| `test_banking_raises_and_off_camber_lowers_the_cornering_limit` | V0 closed form at zero banking; banked > flat > off-camber; friction circle exhausted at the limit speed; infinite limit when steep; a banked lap is faster |
| `test_radius_follows_the_encyclopedia_lateral_g_table` | Exact radius at each class midpoint; held beyond the classes; monotonic; equal-ended spiral = arc |
| `test_every_circuit_is_complete_and_drivable` | 28 circuits; official length; zero net rise; straight scale 0.85–1.6; 305 km lap rule (not Monaco); valid chances; lap time, minimum and maximum speeds in range; Zandvoort banking |
| `test_a_layout_that_cannot_fit_its_length_is_rejected` | `ValueError` |
| `test_hidden_conditions_are_random_within_range_and_reach_the_race` | Hidden pit loss, fuel and wear reach the `Race`; calibrated grip in use; ranges; real variation over 40 seeds; worst-case fuel; a fixed pit loss; the observation shows only the effect (more wear) |
| `test_calibration_and_circuit_settings` | Calibrated and baseline reference laps; circuit defaults (Singapore) and overrides |
| `test_every_circuit_runs_an_episode` | A 2-lap episode on each of the 28 circuits |

| Command | Result |
|---|---|
| `python3 test_simulation.py`, `test_race.py`, `test_tyres_fuel_pits.py`, `test_traffic.py`, `test_weather.py`, `test_race_control.py` | all `ok`: the V0–V5 regression values are unchanged (exact or 1e-12) |
| `python3 test_validation.py` | `ok`: calibration reproducible and matches the committed config; report up to date |
| `python3 test_rl.py` | `ok` (17 tests) |
| `python3 test_research.py` | `ok` (11 tests, including "stored results match the committed code digest, config and report") |
| `python3 test_tracks.py` | `ok` (6 tests) |

**Mutation check (manual, not committed).** In a scratch copy, 17 deliberate bugs were introduced one at a time:

- spiral direction reversed;
- chicane radius taken from the loosest part;
- banking sign flipped in the corner limit;
- banking sign flipped in the friction circle;
- banking sine dropped;
- banking not passed to acceleration;
- radius table not clamped;
- elevation not kept when straights are scaled;
- spiral length halved;
- hidden pit loss not used;
- hidden wear not applied;
- under-fuelling;
- a fixed pit loss ignored;
- calibrated grip not applied;
- circuit safety-car chance ignored;
- track not validated in the research config;
- report error computed against the baseline.

**All 17 were caught on the first run.**

## Deliberately absent

- **Altitude** (air density): Mexico's model lap is 14.6 % faster than its record partly for this reason.
- **Crests and compressions, track width, kerbs.**
- **Per-circuit measured pit losses:** only Monza has data. More Jolpica data would add more non-commercial files.
- **Calibrated values in `main.py`:** it shows the simulator defaults.
- **Changes to the V8 question or decision rule.**

## Known limitations

See [IMPLEMENTATION.md §10](IMPLEMENTATION.md#10-limitations). In short:

- the layouts are approximations, and banking is counted twice where the speed already includes it;
- one Monza-fitted grip is used everywhere;
- the hidden-condition ranges are assumptions;
- the experiments race alone at Monza;
- results describe the simulator, not F1.
