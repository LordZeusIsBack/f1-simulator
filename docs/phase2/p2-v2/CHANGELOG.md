# P2-V2 changelog: driver decision interfaces and rule-based baseline policies

## Commit record

| | |
|---|---|
| Milestone | P2-V2 (Phase 2, milestone 2 of 6) |
| Branch | `ai-agent-branch` (never `main`) |
| Parent (P2-V1) | `c5c24bc` "feat(p2-v1): add driver skill profile with separate attack and defence" |
| Commit message | `feat(p2-v2): add driver observations, actions and rule-based driving policies` |

A commit cannot contain its own hash. The hash is reported in the session summary and can be found with `git log --grep "feat(p2-v2)"`.

Line numbers below are from this commit and may shift in later versions; symbol names are the stable reference.

## Scope

A driver decision interface (observation, actions, policy signature, validation) and three rule-based baseline policies that use the P2-V1 skills, plus a harness that logs their decisions during a race. The actions are proposals only. Out of scope: physical effects of actions (P2-V3), RL (P2-V4), and throttle or brake commands.

## How P2-V2 differs from P2-V1

- **New capability:** a policy can observe any car on track and propose `MAINTAIN_PACE`, `ATTACK`, `DEFEND` or `CONSERVE_TYRES`, with a logged reason.
- **No change to any race result.** No existing module was modified. `driving.run` gives the same finish times and overtakes as `race.run`, and a test checks this.
- **The strategist is unchanged:** same `rl/env.py`, `rl/policies.py`, observation, actions and rewards.

No dependencies added. `main.py` is unchanged. The only new public API is the `driving` module.

## Files

| File | Status | Change |
|---|---|---|
| `driving.py` | new (219 lines) | Driver observation, actions, policy interface, observer, harness, baselines |
| `test_driving.py` | new | 17 tests (below) |
| `docs/phase2/p2-v2/IMPLEMENTATION.md` | new | Schema, actions, interface, baselines, skills, limitations, worked example |
| `docs/phase2/p2-v2/CODE_FLOW.md` | new | One encounter traced from observation to log |
| `docs/phase2/p2-v2/CHANGELOG.md` | new | This file |
| `README.md` | modified | Phase 2 table (P2-V2 done); P2-V2 summary and an example invoking each baseline, with its output; `test_driving.py` in Testing; `driving.py` in Project layout. Phase 1 sections unchanged |
| `research/results/scenario_coverage.json` | regenerated | V8 re-run because the stored code digest covers every non-test `.py` file, including the new `driving.py` |
| `research/results/scenario_coverage.md` | regenerated | Report of the same re-run |

No files deleted, renamed or otherwise modified.

## New symbols (`driving.py`)

| Symbol | Line | Kind | Notes |
|---|---|---|---|
| `ATTACK_SKILL_SPAN` | 18 | constant | 1.0 m/s per unit of `attack`, placeholder |
| `DEFENCE_SKILL_SPAN` | 19 | constant | 0.5 s per unit of `defence`, placeholder |
| `TYRE_SKILL_SPAN` | 20 | constant | 0.2 wear per unit of `tyre_management`, placeholder |
| `DriverAction` | 23 | `Enum` | **New action types:** `MAINTAIN_PACE`, `ATTACK`, `DEFEND`, `CONSERVE_TYRES` |
| `DriverObservation` | 31 | frozen dataclass | **New observation:** `laps_remaining`, `speed`, `on_straight`, `gap_ahead`, `closing_speed`, `gap_behind`, `compound`, `tyre_wear`, `wetness`, `flag`, `overtaking_allowed`, `drs`; validated in `__post_init__` (line 46) |
| `Decision` | 72 | `NamedTuple` | `action`, `reason`, `features` |
| `DriverPolicy` | | type alias | `Callable[[DriverObservation, Driver], Decision]` |
| `DecisionRecord` | 81 | `NamedTuple` | `time`, `car`, `lap`, `action`, `reason`, `features` |
| `available_actions` | 91 | function | Attack needs a car ahead, defend a car behind; both need `overtaking_allowed` |
| `decide` | 101 | function | Rejects a result that is not a `Decision` with a `DriverAction`, or whose action is unavailable |
| `_factor`, `_speed` | 115, 128 | private functions | The time factor of `Race._drive` (pace, dirty air, DRS, race control) and the resulting speed |
| `observe` | 132 | function | Builds a `DriverObservation` for a car on track |
| `run` | 157 | function | Runs the race to the finish, asks each policy before every step, logs changes of action |
| `RuleBasedDriver` | 180 | frozen dataclass | Attack, then defend, then conserve, else maintain; thresholds validated (line 189) |
| `CONSERVATIVE`, `BALANCED`, `AGGRESSIVE`, `BASELINES` | 216-219 | instances | The three styles (thresholds in IMPLEMENTATION.md §7) |

## Reasons for the significant choices

- **One new module, no changes to `race.py`:** the milestone asks only for observing and proposing. Leaving the race untouched guarantees that results do not change.
- **Physical units and `None` in the observation:** easier to read and debug than [0, 1] scaling. P2-V4 can scale for RL, as `rl.env` does.
- **Policy receives the driver separately from the observation:** the profile describes capabilities and the observation describes the situation (master prompt §5). One policy object can drive any driver.
- **One `RuleBasedDriver` class with three settings:** the three styles share one transparent rule order. The labels come from tested threshold differences (IMPLEMENTATION.md §7).
- **Log only changes of action:** the prompt asks not to log whole objects at every step. Policies still decide every step.
- **Private `Race` helpers in `observe`:** avoids changing `race.py`; marked with a `ponytail:` comment.

## Tests

### Added: `test_driving.py`

| Test | Covers |
|---|---|
| `test_observation_rejects_invalid_and_inconsistent_values` | Each field's invalid values, `closing_speed`/`gap_ahead` consistency, negative closing speed allowed |
| `test_observe_reads_gaps_tyres_and_segment_from_a_race` | Leader/middle/last gaps equal `Race.interval`; laps, tyres, segment, flag, wetness |
| `test_missing_data_alone_on_a_dry_track_without_race_control` | `None` gaps, `GREEN`, wetness 0, only maintain and conserve available |
| `test_weather_and_flags_reach_the_observation` | Wet track and VSC appear; attack and defend become unavailable; baselines stay within the available actions |
| `test_observe_refuses_a_car_that_is_not_on_track` | A car in the pits |
| `test_decide_accepts_only_available_driver_actions` | Non-`Decision`, non-`DriverAction` and unavailable actions rejected; availability sets |
| `test_rule_based_driver_thresholds_are_validated` | Negative thresholds and `conserve_wear` > 1 rejected |
| `test_decisions_are_deterministic` | Same input gives the same decision; two harness runs give identical logs |
| `test_baselines_differ_on_when_to_attack` | Five controlled scenarios, expected action of each baseline |
| `test_baselines_differ_on_when_to_defend_and_attack_comes_first` | Defending windows; attack takes priority |
| `test_baselines_differ_on_tyre_conservation` | Conserve thresholds; aggressive never conserves; nothing on the last lap; fighting first |
| `test_attack_skill_lowers_the_closing_speed_needed` | `needed` at attack 0, 0.5 and 1 |
| `test_top_attack_skill_still_needs_to_be_faster` | attack 1.0 with closing speed 0 or negative: no attack from any baseline |
| `test_defence_skill_widens_the_defending_window` | `window` at defence 0, 0.5 and 1 |
| `test_tyre_management_skill_starts_conserving_earlier` | `conserve_from` at 0.5 and 1; aggressive never conserves |
| `test_run_logs_changes_of_action_with_reasons_and_does_not_change_the_race` | Same finish times and overtakes as `race.run`; logged only on change; reason codes; features are numbers |
| `test_run_rejects_policies_for_cars_not_in_the_race` | Unknown car number |

One test-authoring error was found and fixed before the first full pass: the expected value in the conservative weak-defender case.

### Modified, skipped, failing

No existing test modified or skipped. Backward compatibility is covered by the unchanged strategist tests (`test_rl.py`), race tests and P2-V1 tests.

### Results (all run in this session)

| Test file | Result |
|---|---|
| `test_driving.py` (new) | ok |
| `test_drivers.py` | ok |
| `test_race_control.py` | ok |
| `test_race.py` | ok |
| `test_research.py` | ok (after the V8 re-run below) |
| `test_rl.py` | ok (strategist unchanged) |
| `test_simulation.py` | ok |
| `test_tracks.py` | ok |
| `test_traffic.py` | ok |
| `test_tyres_fuel_pits.py` | ok |
| `test_validation.py` | ok |
| `test_weather.py` | ok |

Demonstration: the README example was extracted from `README.md` and run, and its output matches the "Expected output" block exactly.

## V8 research re-run

`python3 -m research.scenario_coverage` was run once after the code was final (2,045 s on this machine, complete, 0 failed episodes). Compared with the P2-V1 results:
- `config`, `training`, `evaluation`, `failed_episodes`, `status` and `python`: **identical**.
- Changed: `revision` (code digest `582c4749…` → `1c481f1f…`, git HEAD `0e72c3e` → `c5c24bc`) and `wall_time_s`. In the `.md` report, only those two lines changed.
- `dirty: True` is expected, because the run was made before the P2-V2 commit. (The P2-V1 run also recorded `0e72c3e`, the commit before P2-V1, for the same reason.)

## Commands executed

```bash
git status -sb; git fetch origin; git log --oneline -1 origin/ai-agent-branch
python3 test_driving.py                         # new tests
python3 - <<'EOF' ... EOF                       # smoke run, closing-speed comparison with OvertakeEvent.advantage, encounter capture
python3 - < README example                      # the README example, extracted from README.md and run
python3 -m research.scenario_coverage           # V8 re-run (digest)
for t in test_*.py; do python3 $t; done       # full suite
git diff                                        # full diff review
```

## Known limitations and deferred features

- **No action has a physical effect** (P2-V3): attack gating, defensive-line cost and the pace-for-wear trade are not implemented.
- Rules use instantaneous values, so actions can flicker within a lap; there is no hysteresis.
- Observations are exact (no noise or delay).
- `observe` depends on `Race`'s private helpers, and `_factor` copies `Race._drive`'s factor calculation. A change to either must be mirrored.
- `consistency` and `wet_weather` do not influence any decision yet. `wetness`, `compound`, `drs` and `speed` are observed but unused by the baselines.
- Policies run only through `driving.run` or direct calls; the strategist environment does not call them (P2-V6 connects the two).
