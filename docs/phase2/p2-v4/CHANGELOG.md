# P2-V4 changelog: trainable AI driver

## Commit record

| | |
|---|---|
| Milestone | P2-V4 (Phase 2, milestone 4 of 6) |
| Branch | `ai-agent-branch` (never `main`) |
| Parent (P2-V3) | `f5ff307` "feat(p2-v3): drive cars by pedals and physics under driver policies" |
| Commit message | `feat(p2-v4): add driving RL environment, driving-dependent wear and Q-learning` |

A commit cannot contain its own hash. The hash is reported in the session summary and can be found with `git log --grep "feat(p2-v4)"`.

Line numbers are from this commit and may shift; symbol names are the stable reference.

## Scope

A reinforcement-learning environment for driving decisions, separate from the strategist's. It comes with baselines, tabular Q-learning, and a seeded experiment with stored configuration and results. It also includes two simulator changes:
- tyre wear that depends on how a controlled car is driven, which the environment needs to pose a real trade-off;
- a fix for a P2-V3 bug found while building the environment.

Not included: connecting the driver to the strategist (P2-V6), several learning drivers in one race (P2-V5), and pedal-level actions.

## How P2-V4 differs from P2-V3

- **New:** `rl.driver_env.DriverEnv`, a Gymnasium-style environment in which the agent picks a `DriverAction` every 250 m for one controlled car in traffic.
- **New:** `rl.driver_learning`, with baselines (three fixed styles and the three P2-V2 rule-based drivers), tabular Q-learning, a parallel seeded experiment and a generated report.
- **Changed behaviour, controlled cars only:**
  1. **Wear follows the driving style.** Per metre, wear is `wear_factor(grip share, tyre_management)` times the full-push rate. ATTACK and DEFEND wear exactly as before. MAINTAIN_PACE and CONSERVE_TYRES wear less, and a better `tyre_management` saves more. Wear still reaches the grip once per lap, at the line.
  2. **DRS no longer lifts the controller's target** (bug fix). The target is divided by `max(factor, 1)`. Before, DRS made the car brake too late, and the corner cap removed the excess for free.
- **Unchanged:**
  - uncontrolled cars, their tyres and every V0–V9 recorded result;
  - the strategist environment, its policies, evaluation and experiments;
  - `physics.py`, `simulation.py`, `traffic.py` and `driving.py`.

**Effect on earlier Phase 2 examples:**
- the P2-V3 README example changed (the aggressive policy no longer passes, because its pass relied on the DRS bug), and the README was updated;
- [P2-V3 IMPLEMENTATION.md](../p2-v3/IMPLEMENTATION.md) §9 and §10 got correction notes;
- the P2-V2 README example has no controlled cars and is unchanged.

**`tyre_management` now has an effect,** but only for controlled cars. P2-V1 listed it as profile only. `test_drivers.test_profile_only_skills_do_not_change_a_race_yet` still passes because it uses uncontrolled cars; only its docstring was updated to say so.

No dependencies added. `main.py` is unchanged.

## Files

| File | Status | Change |
|---|---|---|
| `rl/driver_env.py` | new | `DriverEnv`, `Observation`, `StepResult`, `ACTIONS`, `DECISION_DISTANCE`, `SPEED_SCALE`, `GAP_SCALE`, `CLOSING_SCALE`, `WEAR_PRICE` |
| `rl/driver_learning.py` | new | Baselines (`maintain`, `push`, `conserve`, `RuleBased`, `baselines`), `state`, `QLearner`, `train`, `run_episode`, `experiment`, `summarise`, `report`, `main`, `SETTINGS`, `SMOKE` |
| `rl/reports/driver_experiment.json` | new (generated) | Settings, git revision, every training return, every learned table, every evaluation episode |
| `rl/reports/driver_experiment.md` | new (generated) | Report |
| `control.py` | modified | `WEAR_EXPONENT`, `wear_factor`, `CarControl.load`; `STYLES` comment on CONSERVE_TYRES |
| `tyres.py` | modified | `Tyres.used` (default `None`); `Tyres.wear` uses it when set |
| `race.py` | modified | `_advance_controlled`: `max(factor, 1.0)` (bug fix) and `load` accumulation; `__init__` resets `load`; `_complete_lap` updates `used` for controlled cars |
| `test_driver_env.py` | new | 12 tests (below) |
| `test_drivers.py` | modified | Docstring of `test_profile_only_skills_do_not_change_a_race_yet` only |
| `docs/phase2/p2-v4/IMPLEMENTATION.md`, `CODE_FLOW.md`, `CHANGELOG.md` | new | |
| `docs/phase2/p2-v3/IMPLEMENTATION.md` | modified | Correction notes in §9 (DRS bug; wear now depends on driving) and §10 (example and braking trace values) |
| `docs/phase2/p2-v3/CODE_FLOW.md` | modified | Correction note in §3: the traced step's grip and end speed since P2-V4 |
| `README.md` | modified | Phase 2 table; P2-V1 note (`tyre_management` now used by controlled cars); P2-V3 example output, text and limits; P2-V4 section (driver environment, example, experiment commands and results); a line in "RL environment (V7)" saying it is the strategist environment and pointing to the driver environment; Testing and Project layout |
| `research/results/scenario_coverage.json`, `.md` | regenerated | V8 re-run for the code digest |

No files deleted or renamed.

## Symbols

### New
- **`rl/driver_env.py`:**
  - `DriverEnv(laps, track, team, driver, opponents, wear_price, dt, max_steps, seed, calibration)` (line 61);
  - its methods `reset` (105), `step` (128), `action_mask` (154), `tyre_wear` (161), `_observe` (169) and `_info` (190);
  - `Observation`, 10 fields (38); `StepResult` (53).
- **`rl/driver_learning.py`:**
  - the baselines `maintain` (39), `conserve` (43), `push` (47), `RuleBased` (54) and `baselines` (64);
  - `state` (71), `QLearner` (81) with `act`, `update`, `__call__` and `table`;
  - `train` (124), `run_episode` (148), `_job` and `_map`, `experiment` (183), `summarise` (206), `report` (229), `main` (276).
- **`control.py`:** `WEAR_EXPONENT` (24), `CarControl.load` (59), `wear_factor` (62).
- **`tyres.py`:** `Tyres.used` (35).

### New action and observation types
- **Actions:** the driving environment's action space is the existing `DriverAction` (index order in `ACTIONS`). No new action types.
- **Observation:** a new type, `rl.driver_env.Observation`. The strategist's `rl.env.Observation` is unchanged.

### Public API changes
- `Tyres(compound, laps=0, used=None)`. The new third field is optional, and existing calls and equality checks are unaffected.
- `CarControl(action, speed, clipped, load)`. The new fourth field is optional.

## Reasons for the significant choices
- **Wear before learning:** without it the best driving policy is known ("always the highest grip share"), and an RL result would be meaningless (IMPLEMENTATION.md §2, §3.1).
- **A power law in grip share, with the skill in the exponent:** one line. At the limit every driver wears the same, and below it the skill sets the exchange rate between pace and wear, as P2-V1 defined `tyre_management`.
- **Decisions every 250 m rather than every few seconds:** a fixed-time step would give every action the same time cost, leaving no learning signal (IMPLEMENTATION.md §4.1).
- **The ideal-lap reference in the reward:** it does not change the best policy, but it removes the location noise from each step's reward (§4.4).
- **Skills as environment settings, not observations:** one fixed driver per environment (§4.2).
- **Tabular Q-learning, not CEM or deep RL:** per-step credit assignment, no dependencies, and a readable result (§5.1).
- **A `wear_price = 0` control condition:** its best policy is known, so it tests the learner (§5.2).
- **`wear_price` = 130 chosen on probe seeds 500–511:** it makes the fixed styles roughly equal, so the main condition asks a real question. The probe seeds are in neither training (0–299, 1000–1299, 2000–2299) nor evaluation (10000–10029).

## Tests

### Added: `test_driver_env.py`

| Test | Covers |
|---|---|
| `test_wear_follows_the_grip_share_and_the_tyre_management_skill` | `wear_factor` values and ordering; `Tyres.used` default unchanged; ATTACK gives `used == laps`; CONSERVE and MAINTAIN wear less, more so with skill; uncontrolled tyres unchanged |
| `test_environment_settings_are_validated` | 11 invalid settings rejected |
| `test_reset_and_step_contracts` | Return types, mask length, invalid action types, ≥ 250 m per step, reward = −(time_lost + wear_cost); `step` before `reset` raises |
| `test_unavailable_actions_are_rejected` | Alone: ATTACK and DEFEND masked and rejected |
| `test_observations_stay_in_bounds_and_hide_the_scenario` | Every field in [0, 1] (closing in [−1, 1]) over two episodes; no skill, price or seed fields |
| `test_episode_ends_at_the_finish_and_rewards_add_up` | Termination only at the end; step count; the sum of rewards equals −(finish − ideal + price × wear) exactly; `step` after the end raises; truncation by `max_steps` |
| `test_actions_change_the_motion_time_and_wear` | CONSERVE is > 1 s slower and wears less than MAINTAIN through physics; the action reaches `car.control.action` |
| `test_wear_price_trades_time_against_tyres` | At price 0 MAINTAIN costs less; at 400 CONSERVE does |
| `test_reset_is_deterministic_and_seeds_differ` | Same seed gives an identical episode and scenario; another seed differs |
| `test_baselines_choose_what_their_names_say` | All baselines return allowed actions; fixed styles; `push` priorities; the P2-V2 adapter equals the rule's decision; `None` observation falls back to MAINTAIN |
| `test_q_learning_updates_and_plays_greedily` | Update arithmetic (terminal and bootstrapped), greedy choice among tried actions, fallback, never an unavailable action, state shape |
| `test_training_and_evaluation_are_seeded_and_report` | Two identical training runs give identical returns and tables; `run_episode` fields; `experiment` and `report` end to end (one process, tiny budget) |

### Modified, skipped, failing
- `test_drivers.py`: docstring only.
- No test skipped.

### Results (final code, 2026-10-16/17)

Every test file was run once on the final code. The times are wall times, measured while the experiment and the V8 re-run were also running.

| File | Result | Time |
|---|---|---|
| `test_simulation.py` | ok | 1 s |
| `test_race.py` | ok | 3 s |
| `test_tyres_fuel_pits.py` | ok | 6 s |
| `test_traffic.py` | ok | 8 s |
| `test_weather.py` | ok | 8 s |
| `test_race_control.py` | ok | 15 s |
| `test_validation.py` | ok | 108 s |
| `test_rl.py` (strategist environment regression) | ok | 62 s |
| `test_research.py` (after the V8 re-run; includes the code-digest check) | ok | 40 s |
| `test_tracks.py` | ok | 5 s |
| `test_drivers.py` | ok | 8 s |
| `test_driving.py` | ok | 5 s |
| `test_control.py` | ok | 14 s |
| `test_driver_env.py` | ok | 41 s |

No test failed, and none was skipped.

## Experiment run

`python3 -m rl.driver_learning` with `SETTINGS` (IMPLEMENTATION.md §5.2): 66 min 45 s wall, 183 min CPU, 7 processes. The 2026-10-14 run was not completed (see "Interrupted session and recovery").

- **Training:** 2 wear prices × 3 runs × 300 episodes = 1,800 episodes, about 35,000 decisions per run.
- **Evaluation:** 2 wear prices × 9 policies × 30 held-out seeds = 540 episodes.
- **Stored:** `rl/reports/driver_experiment.json` and `rl/reports/driver_experiment.md`. They record git HEAD `f5ff307` with a dirty tree, because the experiment ran before this commit.

**Result:**
- At wear price 130 (main), the best baseline is `rule conservative` (19.49 s). The three Q-learning runs are worse by +1.11, +1.34 and +0.74 s, and every 95 % interval lies above 0. **The learned policy does not improve on the baseline.**
- At wear price 0 (control), the known optimum `push` costs 0.88 s. The runs are at −0.00, +0.19 and +0.74 s from it.

The analysis is in IMPLEMENTATION.md §6.

## V8 research re-run

`python3 -m research.scenario_coverage` was run once on the final code, on 2026-10-16/17. It took 3,094.6 s (51 min 35 s), slower than usual because the driver experiment ran at the same time; it completed with 0 failed episodes. (The first session's run, 3,067 s, gave the same results but was lost in the reset and was on code with the old docstring.) Compared with the P2-V3 results:
- `config`, `config_path`, `training`, `evaluation`, `failed_episodes`, `status` and `python`: **identical**. The strategist environment creates no controlled cars, so neither the wear change nor the DRS fix reaches it.
- Changed: `revision` (code digest `3f84b8fc…` → `a282894c…`, git HEAD `f402a05` → `f5ff307`) and `wall_time_s` (2,074.9 → 3,094.6 s). In the `.md` report, only those two lines changed.
- `python3 test_research.py` passes against the new results, including the code-digest check.

## Commands executed

```bash
git status -sb; git fetch origin; git log --oneline -6
python3 - <<'EOF' ... EOF          # probes: episode timing, clip locations (found the DRS bug), wear per action and skill,
                                   # hand-written policies on probe seeds 500-511 at wear prices 100 and 130, the CODE_FLOW trace
python3 test_driver_env.py
python3 -m rl.driver_learning --smoke
python3 -m rl.driver_learning      # the experiment
python3 -m research.scenario_coverage
for t in test_*.py; do python3 $t; done
git diff
```

Second session (2026-10-16/17), after the recovery:

```bash
git fetch origin; git status --short; git log --oneline -5; git reflog -8; git fsck --no-reflogs --unreachable
python3 test_driver_env.py; python3 test_control.py; python3 test_race.py; python3 test_tyres_fuel_pits.py
python3 test_drivers.py; python3 test_driving.py
python3 -m rl.driver_learning --smoke
python3 - <<'EOF' ... EOF          # README P2-V3 example, CODE_FLOW trace, P2-V3 braking-trace check, README P2-V4 example
python3 -m rl.driver_learning      # the experiment (66 min 45 s)
python3 -m research.scenario_coverage   # V8 re-run (51 min 35 s), at the same time
for t in test_*.py; do python3 $t; done   # test_research.py after the V8 re-run
git diff
```

An exploratory training run (3 runs × 150 episodes, wear price 100, training seeds only) was made before the code was final. It was used only to check that training runs. It is not part of the results.

### Interrupted session and recovery

P2-V4 was built over two sessions:
1. **2026-10-14:** the code, tests and documentation were written and the tests passed. The session ended while the experiment was still running, so nothing was committed and no results were stored.
2. **2026-10-16:** `git reflog` showed `reset: moving to HEAD` at 23:21:52 UTC, which discarded the uncommitted changes to tracked files (`control.py`, `tyres.py`, `race.py`, `test_drivers.py`, `README.md`, the P2-V3 docs). The new, untracked files survived. The reset did not come from a Claude session, and no stash was left.

Recovery:
- Each lost edit was re-applied from the first session's record of exact before/after text, then checked against this changelog's symbol list and line references.
- The P2-V3 IMPLEMENTATION note on §9 was placed after the whole bullet; the first session's version split that line.
- Re-checked after recovery: the P2-V3 README example (382.342 / 382.342 / 381.930 / 381.629 s), the CODE_FLOW trace (11 race steps, reward −0.1726, finish 79.082 s, return −4.081), and the P2-V3 braking-trace correction (grip 1.7973, end speed 93.994 m/s).
- One code change in the second session: the `rl/driver_learning.py` docstring's time estimate ("~15 min") was removed, because it was wrong (see "Experiment run").
- One documentation fix: IMPLEMENTATION.md §3.1 cited `race.py:456` for the wear accumulation; the lines are 460 and 466.
- The experiment and the V8 re-run were then run from scratch on the final code.

## Known limitations and deferred features

- The wear model (`WEAR_EXPONENT`, the power law) and the wear price are placeholders. Wear follows the planned grip share, not the measured tyre load.
- The environment is narrow: one track, 5 laps, mediums, dry, no race control or pits, non-reacting profile-driven rivals, and one fixed driver.
- The action mask caps solo pace at 97 % of the grip (P2-V2 rule).
- Q-learning uses a hand-designed 144-state discretisation and a small budget (300 episodes × 3 runs).
- DRS does nothing for controlled cars, and there is still no lateral model (P2-V3).
