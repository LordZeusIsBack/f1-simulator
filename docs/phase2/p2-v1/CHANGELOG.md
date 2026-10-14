# P2-V1 changelog: driver skills and profiles

## Commit record

| | |
|---|---|
| Milestone | P2-V1 (Phase 2, milestone 1 of 6) |
| Branch | `ai-agent-branch` (never `main`) |
| Parent | `0e72c3e` "docs(v9): record version commit hash in changelog" |
| Commit message | `feat(p2-v1): add driver skill profile with separate attack and defence` |

A commit cannot contain its own hash. Unlike Phase 1, Phase 2 adds no follow-up commit to record it. The hash is reported in the session summary and can be found with `git log --grep "feat(p2-v1)"`.

Line numbers below are from this commit and may shift in later versions; symbol names are the stable reference.

## Scope

Extend `drivers.Driver` with five skills: `attack`, `defence`, `tyre_management`, `consistency` and `wet_weather`. Wire `attack` and `defence` into the existing overtaking rule. Store and validate the other three without any effect. No driver decisions, no new car controls, no RL driver: those are P2-V2 to P2-V4.

## How P2-V1 differs from V9

- **With default drivers, or drivers configured only by `pace` and `racecraft`, every result is identical to V9.** All recorded-value regression tests (V0–V5) pass unchanged, and the README's V3 traffic example prints the same times to the millisecond.
- **New behaviour:** a driver's `attack` and `defence` can differ. The required speed advantage for a pass now uses the attacker's `attack` and the defender's `defence`, not both drivers' `racecraft`.
- **No behaviour from `tyre_management`, `consistency` or `wet_weather`.** A test checks that changing them leaves a wet race with tyre wear and traffic bit-identical.

No dependencies added. No entry point changed (`main.py` is untouched). `TrafficRules` field names are unchanged.

## Files

| File | Status | Change |
|---|---|---|
| `drivers.py` | modified | Five new fields on `Driver`; `__post_init__` resolves `attack`/`defence` and validates every skill in one loop; docstring and `racecraft` comment updated |
| `traffic.py` | modified | `required_advantage` reads `attacker.attack` and `defender.defence`; comments on `TrafficRules.overtake_margin` and `racecraft_effect` updated |
| `test_drivers.py` | new | 9 tests (below) |
| `docs/phase2/p2-v1/IMPLEMENTATION.md` | new | Definitions, design, equations, limitations, worked example |
| `docs/phase2/p2-v1/CODE_FLOW.md` | new | Construction, storage and use of a `Driver` in a race |
| `docs/phase2/p2-v1/CHANGELOG.md` | new | This file |
| `README.md` | modified | New "Phase 2: AI driver" section with status and links; `test_drivers.py` in Testing; `drivers.py` row in Project layout. Phase 1 sections unchanged |
| `research/results/scenario_coverage.json` | regenerated | V8 experiment re-run because its stored code digest covers `drivers.py` and `traffic.py` (see "V8 research re-run") |
| `research/results/scenario_coverage.md` | regenerated | Report of the same re-run |

No files deleted or renamed.

## Symbols

### `drivers.py`

| Symbol | Status | Detail |
|---|---|---|
| `Driver` docstring (line 8) | modified | Profile = abilities, not decisions; points to these docs |
| `Driver.name`, `Driver.pace` | inherited, unchanged | |
| `Driver.racecraft` (line 13) | inherited; meaning clarified | Now documented as the general wheel-to-wheel skill and the default for `attack`/`defence`. Default still 0.5. Not deprecated |
| `Driver.attack` (line 14) | new | `float \| None = None`; `None` becomes `racecraft` |
| `Driver.defence` (line 15) | new | `float \| None = None`; `None` becomes `racecraft` |
| `Driver.tyre_management` (line 16) | new, profile only | `float = 0.5` |
| `Driver.consistency` (line 17) | new, profile only | `float = 0.5` |
| `Driver.wet_weather` (line 18) | new, profile only | `float = 0.5` |
| `Driver.__post_init__` (line 20) | modified | (1) fills `attack`/`defence` from `racecraft` via `object.__setattr__` (the class is frozen); (2) checks every field after `name`, not just `pace` and `racecraft`. Same check and same error text as V3 |
| `Driver.time_factor` (line 29) | inherited, unchanged | |
| `PACE_SPREAD` | inherited, unchanged | |

Validation was already strict enough for the new requirements. The V3 check `not 0 <= value <= 1` already rejects NaN and ±∞, and the `bool` check already rejects `True`/`False`. P2-V1 only extends it to all skills.

### `traffic.py`

| Symbol | Status | Detail |
|---|---|---|
| `required_advantage` (line 45) | modified | `overtake_margin − racecraft_effect × (attacker.attack − defender.defence)`; was `(attacker.racecraft − defender.racecraft)` |
| `can_attack` | unchanged code; new inputs | Calls `required_advantage`, so it now uses `attack`/`defence` |
| `TrafficRules.overtake_margin`, `racecraft_effect` | comments only | Same names, defaults (2.0 m/s, 1.0 m/s) and meaning, restated in terms of attack − defence |

### Public API

- `Driver(...)` accepts five new keyword arguments. The first three positions (`name`, `pace`, `racecraft`) are unchanged.
- `Driver.__repr__` and `==` now include the new fields. `Driver(racecraft=0.7) == Driver(racecraft=0.7, attack=0.7, defence=0.7)` is `True`, because both resolve to the same values.
- No new actions or observations. The strategist's `rl.env.Observation` and `ACTIONS` are unchanged.

## Reasons for the significant changes

- **Split instead of add (`required_advantage`):** the V3 term already compared an attacker's skill with a defender's skill. Splitting it into two named skills gives the prompt's independent `attack` and `defence` without a new constant or a performance bonus (IMPLEMENTATION.md §5.3).
- **`None` defaults for `attack`/`defence`:** a numeric default would change every existing `Driver(racecraft=x)` with x ≠ 0.5 (IMPLEMENTATION.md §5.4).
- **Three skills profile only:** each needs a mechanism that does not exist yet: a tyre-saving decision and fractional wear, seeded lap-to-lap variation, or a driver margin on low grip. Adding a fixed multiplier now would be the "performance multiplier instead of behaviour" the master prompt rules out (IMPLEMENTATION.md §4.5–4.7).

## Tests

### Added: `test_drivers.py`

| Test | What it checks |
|---|---|
| `test_existing_constructors_and_time_factor_still_work` | `Driver()`, `Driver(name=...)`, V3 positional order, `time_factor()` values 1.0 / 1.005 / 1.01 |
| `test_every_skill_has_its_documented_default` | Field order and every default |
| `test_lower_middle_and_upper_values_are_stored` | 0, 0.0, 0.5, 1, 1.0 for every skill |
| `test_invalid_values_are_rejected_with_the_skill_named` | `True`, `False`, `"0.5"`, NaN, +∞, −∞, −0.01, 1.01, a list, and `None` (except `attack`/`defence`); the error names the skill |
| `test_attack_and_defence_default_to_racecraft_unless_given` | Fallback to `racecraft`, override of one role, equality of resolved profiles, invalid `racecraft` reported as `racecraft` |
| `test_two_drivers_keep_independent_frozen_profiles` | Two fully different profiles; assignment raises `FrozenInstanceError` |
| `test_required_advantage_uses_attacker_attack_and_defender_defence_only` | Formula values; the defender's attack and the attacker's defence have no effect |
| `test_defence_alone_decides_whether_a_pass_happens` | In a 6-lap race, defence 0 lets a faster car pass; defence 1 holds it behind; the defender's own attack makes no difference |
| `test_profile_only_skills_do_not_change_a_race_yet` | Wet race with tyre wear and traffic: identical finish times and overtakes with the three profile-only skills at 0 and at 1 (also a determinism check) |

Mutation check: with `required_advantage` temporarily patched back to the V3 `racecraft` formula (in a separate process, files unchanged), both attack/defence behaviour tests fail. So they do test the new code.

### Modified, skipped, failing

No existing test was modified or skipped. The existing racecraft tests (`test_traffic.test_driver_attributes_are_validated`, `test_racecraft_decides_a_close_fight`, `test_v3_race_results_unchanged_without_weather`) pass unchanged. This shows that `racecraft` keeps its V3 meaning when `attack` and `defence` are not given.

### Results (all run in this session)

| Test file | Before changes | After changes |
|---|---|---|
| `test_drivers.py` | (new) | ok |
| `test_race_control.py` | ok | ok |
| `test_race.py` | ok | ok |
| `test_research.py` | ok | ok (after the V8 re-run below; before it, the stored-digest test fails as expected) |
| `test_rl.py` | ok | ok |
| `test_simulation.py` | ok | ok |
| `test_tracks.py` | ok | ok |
| `test_traffic.py` | ok | ok |
| `test_tyres_fuel_pits.py` | ok | ok |
| `test_validation.py` | ok | ok |
| `test_weather.py` | ok | ok |

Demonstrations run:
- the Monza example in IMPLEMENTATION.md §10 (the V3 profile reproduces the README's V3 output exactly);
- `python3 main.py 3` (unchanged entry point, runs normally).

## V8 research re-run

`research.runner.code_digest()` hashes every non-test `.py` file, and `test_research.test_committed_results_match_the_committed_code_config_and_report` requires the stored results to carry the current digest. Changing `drivers.py` and `traffic.py` therefore requires a re-run, even when results cannot change.

`python3 -m research.scenario_coverage` was run once after the code was final (2,062 s on this machine, complete, 0 failed episodes). Compared with the V9 results:
- `config`, `training`, `evaluation`, `failed_episodes`, `status` and `python`: **identical**. Every number and every verdict is the same, as expected, because the strategist uses only default drivers.
- Changed: `revision` (code digest `88b54f1a…` → `582c4749…`, git HEAD `7bfd66a` → `0e72c3e`) and `wall_time_s`. In the `.md` report, only those two lines changed.
- `dirty: True` is expected: the run was made before the P2-V1 commit, as in Phase 1.

## Commands executed

```bash
git remote -v; git branch -vv; git fetch origin; git status -sb; git log --oneline -12
for t in test_*.py; do python3 $t; done        # before changes: all 10 files "ok"
python3 test_drivers.py                          # new tests
python3 - <<'EOF' ... EOF                        # mutation check and Monza demo (IMPLEMENTATION.md §10)
python3 -m research.scenario_coverage            # V8 re-run (digest)
for t in test_*.py; do python3 $t; done        # after changes: all 11 files
git diff                                         # full diff review
```

## Known limitations and deferred features

- `tyre_management`, `consistency`, `wet_weather`: no effect until a later milestone (planned mechanisms in IMPLEMENTATION.md §4.5–4.7). `test_profile_only_skills_do_not_change_a_race_yet` must be updated when one gains an effect.
- Attack and defence are linear, symmetric, deterministic, and free (defending costs no time). They do not affect a pass once it has started.
- No driver decides anything yet: every follower attempts a pass whenever the rule allows (P2-V2).
- `TrafficRules.racecraft_effect` keeps its V3 name although it now scales attack − defence.
- Skill values are configurable inputs, not ratings of real drivers.
