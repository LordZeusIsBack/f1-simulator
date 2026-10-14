# P2-V3 changelog: on-track driving control

## Commit record

| | |
|---|---|
| Milestone | P2-V3 (Phase 2, milestone 3 of 6) |
| Branch | `ai-agent-branch` (never `main`) |
| Parent (P2-V2) | `f402a05` "feat(p2-v2): add driver observations, actions and rule-based driving policies" |
| Commit message | `feat(p2-v3): drive cars by pedals and physics under driver policies` |

A commit cannot contain its own hash. The hash is reported in the session summary and can be found with `git log --grep "feat(p2-v3)"`.

Line numbers below are from this commit and may shift in later versions; symbol names are the stable reference.

## Scope

A bounded longitudinal control model (throttle and brake), its numerical integration, a braking look-ahead, a speed controller, opt-in controlled cars in `Race`, and the connection from P2-V2 driving policies to that controller. Not included: lateral dynamics, driving-dependent tyre wear, physical DRS and dirty air, RL.

## How the movement model differs from the precomputed-profile model

| | Profile model (V1–P2-V2, still the default) | Control model (P2-V3, opt-in) |
|---|---|---|
| Opt-in | `RaceCar(...)` | `RaceCar(..., control=CarControl())` |
| State | distance only; speed read from the profile | distance **and** speed (`CarControl.speed`) |
| One race step | distance ← `profile.distance_at(time_at(d) + dt / factor)` | sub-steps of ≤ `control_step` (0.02 s): target from `BrakingEnvelope`, pedals from `track_speed`, then speed and distance from `step_motion` |
| Driver pace, dirty air, DRS, flags | stretch profile time by `factor` | divide the controller's **target speed** by the same `factor`; the car reaches it through physics |
| Braking | built into the profile (backward pass with `physics.deceleration`) | planned by `BrakingEnvelope` (backward pass with `control.acceleration` at full brake, correct gravity sign, safer of two speed estimates) and carried out sub-step by sub-step |
| Corner limit | built into the profile | the controller plans within it; `Race` caps any excess at the real limit and counts it (`CarControl.clipped`) |
| After being held up | jumps back to profile speed | accelerates through physics |
| Driver decisions | logged only | `driving.run` sets `car.control.action`, which sets the grip share (1.0 / 1.0 / 0.97 / 0.90) |

**What old behaviour remains available.** Everything. A car without `control` is moved by `_advance` exactly as before, so every recorded-value regression test (V0–V5), the traffic, weather and race-control tests, the V6 validation, the V7 strategist and the V8 research results are unchanged. `physics.py`, `simulation.py`, `traffic.py`, `tracks.py` and `rl/` are untouched. `test_uncontrolled_cars_are_unaffected_by_a_controlled_car` checks that an uncontrolled car's finish time is identical whether the other car is controlled or not (traffic off).

No dependencies added. `main.py` unchanged.

## Files

| File | Status | Change |
|---|---|---|
| `control.py` | new (136 lines) | `Control`, `CarControl`, `acceleration`, `step_motion`, `track_speed`, `BrakingEnvelope`, `braking_envelope`, `STYLES`, `CONTROL_STEP`, `MAX_CONTROL_STEP`, `CLIP_TOLERANCE`, `COAST`, `FULL_THROTTLE`, `FULL_BRAKE` |
| `race.py` | modified (+66 lines) | `RaceCar.control`; `Race(control_step=...)` and its validation; flying-start speed for controlled cars; `_advance` dispatch; new `_advance_controlled` and `_held_speed`; `_free_distance` and `_speed` use a controlled car's actual speed |
| `driving.py` | modified (+5/−2) | `_speed` goes through `race._speed`; `run` copies each decision into `car.control.action`; `run` docstring updated |
| `test_control.py` | new | 15 tests (below) |
| `docs/phase2/p2-v3/IMPLEMENTATION.md` | new | Assessment, equations, integration, look-ahead, controller, time step, limitations |
| `docs/phase2/p2-v3/CODE_FLOW.md` | new | A controlled car braking for Monza's first corner, sub-step by sub-step |
| `docs/phase2/p2-v3/CHANGELOG.md` | new | This file |
| `README.md` | modified | Phase 2 table (P2-V3 done); P2-V3 summary and an example with its output; `test_control.py` in Testing; `control.py` in Project layout. Phase 1 sections unchanged |
| `research/results/scenario_coverage.json`, `.md` | regenerated | V8 re-run for the code digest (see below) |

No files deleted or renamed.

## Symbols

### New (`control.py`)

| Symbol | Line | Detail |
|---|---|---|
| `CONTROL_STEP` | 21 | 0.02 s, default physics sub-step |
| `MAX_CONTROL_STEP` | 22 | 0.05 s, largest allowed |
| `CLIP_TOLERANCE` | 23 | 1e-6 m/s before a corner-limit excess counts |
| `STYLES` | 26 | `DriverAction` to grip share: ATTACK 1.0, DEFEND 1.0, MAINTAIN_PACE 0.97, CONSERVE_TYRES 0.90 |
| `Control` | 35 | Frozen dataclass `(throttle, brake)`, each 0–1, not both > 0, validated |
| `COAST`, `FULL_THROTTLE`, `FULL_BRAKE` | 49 | Constant controls |
| `CarControl` | 53 | Mutable dataclass `(action, speed, clipped)` |
| `acceleration` | 60 | m/s² from pedals, reusing `physics.longitudinal_grip` and `physics.aero` |
| `step_motion` | 69 | One sub-step: Euler speed (floored at 0), trapezoid distance; validates h and v |
| `track_speed` | 82 | Inverse-dynamics speed controller |
| `BrakingEnvelope` | 95 | Backward-pass look-ahead; `point(x)`, `target(x)`, `_entry`, `_index` |
| `braking_envelope` | 135 | `lru_cache(maxsize=64)` wrapper |

### Modified

| Symbol | File | Change |
|---|---|---|
| `RaceCar.control` | `race.py:49` | New field, default `None` |
| `Race.__init__` | `race.py` | New keyword `control_step` (validated to (0, 0.05] s); controlled cars get their profile speed at the grid slot and `clipped = 0` |
| `Race._advance` | `race.py:397` | Two lines: hands controlled cars to `_advance_controlled` |
| `Race._advance_controlled` | `race.py:426` | New: the controlled movement loop |
| `Race._held_speed` | `race.py:465` | New: speed of the car ahead, for a controlled car held behind it |
| `Race._free_distance`, `Race._speed` | `race.py` | Controlled car: present speed × time, and actual speed |
| `driving._speed` | `driving.py` | Calls `race._speed`, so observations report a controlled car's real speed. Uncontrolled values are unchanged (same formula) |
| `driving.run` | `driving.py` | Sets `car.control.action = decision.action` for controlled cars |

**Public API additions:** `RaceCar(control=...)`, `Race(control_step=...)` and the `control` module. There are no changes to any existing signature's meaning, no new action types, and no observation fields.

## Reasons for the significant choices

- **Opt-in per car, dispatch inside `_advance`:** one entry point keeps every caller (traffic, race control, SC queue, lap completion) working for controlled cars, and leaves uncontrolled cars byte-for-byte on the old path.
- **Throttle and brake only:** the existing physics represents exactly these. A lateral control would need a lateral model, which the prompt asks not to fake.
- **The braking envelope as look-ahead:** the car's position and speed alone cannot tell it where to brake. A backward pass over the track points is the smallest representation that can. It uses `control.acceleration`, so it is consistent with the integrator, rather than the profile's speed trace.
- **Safer of two estimates in the envelope:** found by testing all 28 circuits. The plain one-evaluation pass clipped 0.3 m/s at Spa. Keeping the second estimate clipped hundreds of times at Interlagos (−23.9 % downhill Esses). Keeping the lower of the two leaves 6 clips under 0.05 m/s across all circuits at the default sub-step.
- **Inverse-dynamics controller:** acceleration is linear in each pedal, so the exact pedal for a target is a single division. It needs no gains and no tuning.
- **`factor` on the target:** keeps pace, dirty air, VSC/SC/yellow and DRS meaning something for controlled cars without new physics. Its limits are documented (DRS has no effect).
- **0.02 s default sub-step:** within 0.3 % of the ideal profile lap on every circuit, clips under 0.05 m/s, and about 0.08 s of computation per Monza lap (IMPLEMENTATION.md §8).
- **`physics.deceleration` sign left as is:** fixing it would change every recorded V0–V9 result and the calibration. It is reported for a separate decision.

## Tests

### Added: `test_control.py`

| Test | Covers |
|---|---|
| `test_control_inputs_are_validated` | Pedals out of range, NaN, ∞, bool, str, `None`, both pressed; `step_motion` rejects bad h and v; `Race` rejects bad `control_step` |
| `test_throttle_and_brake_change_speed_and_distance` | Full > half > coast > brake in new speed; coasting loses speed to drag; trapezoid distance |
| `test_repeated_steps_accelerate_to_top_speed_then_brake_to_a_stop_without_reversing` | 60 s of throttle: speed rises monotonically to the drag-limited top speed; then braking reaches exactly 0 and stays there; no rolling back uphill |
| `test_speed_controller_matches_reachable_targets` | Reachable targets hit exactly in one sub-step; unreachable ones saturate the pedal |
| `test_braking_envelope_falls_to_the_corner_limit_before_each_corner` | Segment transition at 500 m; the target equals the corner limit in the corner and falls through the braking zone; a lower grip share gives lower targets everywhere |
| `test_controlled_car_brakes_before_the_corner_and_respects_its_limit` | Speed peaks between 400 and 495 m, then falls before the corner at 500 m; never above the corner limit; no clips |
| `test_targets_above_the_grip_limit_are_capped_and_counted` | A controller aiming 30 % past the grip (patched `STYLES`) is capped at the limit and the clips are counted |
| `test_lap_times_are_stable_across_sub_steps_and_match_the_profile` | Sub-steps 0.005 / 0.02 / 0.05 s agree within 0.2 % and match `simulate_lap` within 0.3 %; race `dt` 0.02 vs 1.0 s agree within 10⁻⁴ s |
| `test_controlled_race_is_deterministic` | Identical finish times, overtakes and logs on replay (traffic on, a policy in control) |
| `test_each_action_changes_speed_and_lap_time` | ATTACK < MAINTAIN < CONSERVE in lap time; reversed in minimum corner speed; DEFEND = ATTACK; CONSERVE corner speed = `corner_speed` at 0.9 μ |
| `test_a_driving_policy_changes_how_the_car_moves` | Policies through `driving.run` change finish times (maintain < switch < conserve); the switching policy's log; a decision reaches `car.control.action` |
| `test_observation_reports_the_controlled_speed` | `observe(...).speed == car.control.speed` |
| `test_uncontrolled_cars_are_unaffected_by_a_controlled_car` | An uncontrolled car's finish time is identical next to a controlled or uncontrolled rival (traffic off) |
| `test_controlled_car_is_held_in_traffic_until_it_passes` | Held up behind a slower car; gets ahead only through a logged pass, at that pass's time |
| `test_controlled_car_pits_finishes_and_slows_under_a_vsc` | Pit stop, lap count and finish work; a 30 s VSC costs more than 5 s |

Test-authoring errors found and fixed before the first full pass:
- an unreachable controller target (40 m/s in one 0.02 s sub-step);
- a test policy that returned `ATTACK` with no car ahead, which `decide` rejected correctly.

### Modified, skipped, failing

No existing test was modified or skipped.

### Results (all run in this session)

| Test file | Result |
|---|---|
| `test_control.py` (new) | ok |
| `test_drivers.py` | ok |
| `test_driving.py` | ok |
| `test_race_control.py` | ok (V4/V5 recorded-value regressions) |
| `test_race.py` | ok (V1 recorded-value regression) |
| `test_research.py` | ok (after the V8 re-run below) |
| `test_rl.py` | ok (strategist environment unchanged) |
| `test_simulation.py` | ok (V0 lap-time regression) |
| `test_tracks.py` | ok (V9 circuits) |
| `test_traffic.py` | ok (V3 recorded-value regression) |
| `test_tyres_fuel_pits.py` | ok (V2 recorded-value regression) |
| `test_validation.py` | ok (V6 calibration and report up to date) |
| `test_weather.py` | ok |

Demonstrations:
- the P2-V3 README example, extracted from `README.md` and run: output matches the "Expected output" block exactly;
- the P2-V2 README example re-run: all 7 output lines unchanged.

## V8 research re-run

`python3 -m research.scenario_coverage` was run once after the code was final (2,075 s, complete, 0 failed episodes). Compared with the P2-V2 results:
- `config`, `training`, `evaluation`, `failed_episodes`, `status` and `python`: **identical**.
- Changed: `revision` (code digest `1c481f1f…` → `3f84b8fc…`, git HEAD `c5c24bc` → `f402a05`) and `wall_time_s`. In the `.md` report, only those two lines changed.
- `dirty: True` is expected, because the run was made before this commit.

## Commands executed

```bash
git status -sb; git fetch origin; git log --oneline -1 origin/ai-agent-branch
python3 - <<'EOF' ... EOF        # measurements: lap time vs profile per sub-step on all 28 circuits, clip locations and sizes,
                                 # race-dt sensitivity, envelope build time, the CODE_FLOW sub-step trace, README example search
python3 test_control.py          # new tests
python3 - < README example       # extracted from README.md and run; output matches
python3 -m research.scenario_coverage
for t in test_*.py; do python3 $t; done
git diff
```

## Known limitations and deferred features

- **No lateral model.** `DEFEND` is pushing at the limit; there is no defensive line, racing line or lane.
- **`CONSERVE_TYRES` costs time but saves no wear.** Wear must depend on the grip share before P2-V4 trains a driver.
- **DRS gives a controlled car nothing, and dirty air only lowers its corner target.** Physical drag and downforce effects are not modelled.
- **Held-behind speed** is approximate for an uncontrolled car ahead (its profile speed ÷ its pace).
- **Clips:** under 0.05 m/s on steep downhill corners at the default sub-step; up to about 0.5 m/s at the maximum sub-step; and when wetness jumps.
- **The pedal command is not stored** on `CarControl`.
- **`physics.deceleration` gravity sign:** a pre-existing inconsistency, reported and not changed.
