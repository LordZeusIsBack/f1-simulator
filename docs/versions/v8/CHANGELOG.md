# V8 changelog: advanced strategy research

## Commit record

| | |
|---|---|
| Branch | `ai-agent-branch` (never `main`) |
| Parent (V7) | `3ef534b` "docs(v7): record version commit hash in changelog" (V7 code is in `66207f4`) |
| V8 version commit | `PENDING` |
| Commit message | `feat(v8): add scenario-coverage strategy research experiment` |

As in earlier versions, the hash is recorded by a follow-up commit, `docs(v8): record version commit hash in changelog`, which changes only this table.

The stored results record `git_head` = `3ef534b` (V7) with `dirty: true`, because they were produced before this commit existed. The binding link between results and code is `revision.code_digest`. `test_committed_results_match_the_committed_code_config_and_report` checks that the digest equals the digest of the committed code.

Line numbers refer to the V8 version commit.

## How V8 differs from V7

- **Unchanged:** the simulator (V0–V5), the validation tooling (V6) and the RL environment, policies, evaluation and experiment (V7). All earlier tests pass unchanged.
- **New:** a `research/` package for one controlled experiment (which training-race mix to tune on), with configuration files, a parallel and failure-tolerant runner, bootstrap statistics, a batched CEM, stored results tied to the code, and a report.

No dependencies added. Parallel runs use the standard library's `multiprocessing` with fork.

## 1. Code implementation

| File | Status | Contents |
|---|---|---|
| `research/config.py` (131 lines) | **new** | `ConfigError` (19–20); `load_config` (43–51); `validate` (54–131): strict keys, types, ranges, equal budgets, held-out seeds after the per-run shift, bounds, baselines. `SEED_STRIDE = 7919`. |
| `research/runner.py` (76 lines) | **new** | `EpisodeSpec` (15–18), `env_key` (21–22), `stratum` (25–29), `run_spec` (35–45: reuses V7 `run_episode`; returns errors instead of raising), `run_specs` (48–53: order-preserving, 1 or more processes), `code_revision` (56–65), `code_digest` (68–76) |
| `research/stats.py` (29 lines) | **new** | `summary` (6–10), seeded percentile `bootstrap_ci` (13–20), `paired` (23–29) |
| `research/cem.py` (37 lines) | **new** | `cross_entropy` (10–37): batched; failed candidates counted and never elites; returns the hand-set score too |
| `research/scenario_coverage.py` (204 lines) | **new** | `training_specs` (34–39), `train` (42–61), `evaluate` (64–73), `aggregate` (76–93), `verdict` (96–108, the decision rule), `run` (111–139), `save` (142–147, JSON plus a Markdown report rendered from the stored JSON), `report` (150–200) |
| `research/configs/scenario_coverage.json` | **new** | The experiment configuration, including the question and the decision rule fixed before running |
| `research/configs/smoke.json` | **new** | A 4-lap pipeline check; not a research result |
| `test_research.py` (229 lines) | **new** | See the tests table |
| `docs/versions/v8/*.md`, `README.md` | new / modified | |

The simulator modules, `rl/`, `validation/`, `data/`, all earlier tests, `pyproject.toml` and `uv.lock` are **unchanged**. Nothing was removed.

## 2. Successful execution

| Run | What | Outcome |
|---|---|---|
| Smoke (`smoke.json`) | Pipeline check | Completed in about 20 s; output deleted (not a result) |
| Full run 1 | `scenario_coverage.json`, 7 processes | Completed: 0 failed episodes, 30.5 min, code digest `67ad4b18…`. **Results superseded**, see below. |
| Full run 2 (committed) | Same config, after one fix | Completed: 0 failed episodes, 30.6 min, code digest `b6ab7471…` (equal to the committed code). **Training and evaluation results identical to run 1**, compared in full. |

**Why there are two runs.** The final test found that the Markdown report regenerated from the stored JSON differed from the one written during the run. The JSON stores dictionary keys sorted, which changed the env display order and moved the `rule-based` row. `save()` now renders the report from the stored JSON, and `report()` puts rows in an explicit order. That is a code change, so the code digest changed, and the experiment was re-run so the committed results belong to the committed code. The scientific results did not change.

Nothing planned was left unexecuted: training (6 runs) and both evaluations (main and sensitivity) ran in full, twice.

## 3. Measured results (copied from `research/results/scenario_coverage.md`)

**Held-out paired difference against hand-set rule-based** (40 races, pit_loss 22 s; positive = slower):

| Policy | Mean (s) | 95 % CI (s) | Better / worse / tie |
|---|---|---|---|
| fixed one-stop | +5.01 | [+0.96, +10.30] | 4 / 36 / 0 |
| tuned random run 0 | +1.21 | [−0.10, +3.45] | 8 / 27 / 5 |
| tuned random run 1 | +0.43 | [+0.16, +0.81] | 1 / 34 / 5 |
| tuned random run 2 | +0.80 | [−0.10, +2.21] | 7 / 27 / 6 |
| tuned stratified run 0 | +1.35 | [+0.04, +3.54] | 8 / 28 / 4 |
| tuned stratified run 1 | 0.00 | [0, 0] | 0 / 0 / 40 (hand-set returned) |
| tuned stratified run 2 | +0.80 | [−0.10, +2.21] | 7 / 27 / 6 |

**Decision rule.** Random: 0 of 3 runs with a CI below 0, so it does **not** help. Stratified: 0 of 3, so it does **not** help.

**Sensitivity at pit_loss 25.62 s.** Same verdicts. Fixed one-stop vs rule: +2.64 s, CI [−0.92, +7.23].

**Training gains on the training races:** 4.28, 0.40, 0.06 s per race (random) and 0.55, 0.00, 0.08 s per race (stratified).

## 4. Conclusions supported by the results

Valid **for this simulator only**, with its V6-identified placeholder parameters.

| Conclusion | Status |
|---|---|
| Stratifying the training races does not make 4-threshold CEM tuning beat the hand-set rule at this budget | **Supported** (decision rule: no) |
| Neither training design improves on the hand-set rule on held-out races | **Supported** |
| The tuning overfits its training races (e.g. −4.3 s on training, +1.2 s on held-out) | **Supported** |
| The hand-set rule beats a fixed one-stop at pit loss 22 s | **Supported** (CI [+0.96, +10.30]) |
| That advantage persists at the V6-measured pit loss | **Not supported** (CI includes 0) |
| Tuning makes policies slightly worse for every design | **Inconclusive** (2 of 6 runs have CIs above 0) |
| The hand-set rule is optimal / anything about real F1 | **Not claimed** |

## Tests executed

All commands were run from the repository root on Python 3.12.3.

| Test | Lines | Covers |
|---|---|---|
| `test_committed_configs_load` | 59–62 | configuration loading |
| `test_invalid_configurations_are_rejected` | 65–100 | 19 invalid configs, bad JSON, missing file |
| `test_statistics_on_known_numbers` | 103–119 | summary, paired and bootstrap on known values; the bootstrap definition |
| `test_runner_is_order_preserving_parallel_safe_and_survives_failures` | 122–132 | parallel equals serial, input order kept, failed episode captured, strata |
| `test_research_policies_fit_the_v7_interface` | 135–140 | agent and environment compatibility |
| `test_cem_is_reproducible_and_skips_failed_candidates` | 143–154 | reproducibility; failed candidates never become elites |
| `test_training_rejects_candidates_whose_episodes_fail` | 157–170 | failure handling inside training |
| `test_verdict_applies_the_preregistered_decision_rule` | 173–183 | the decision rule |
| `test_experiment_runs_is_reproducible_and_stores_config_and_revision` | 186–199 | end-to-end reproducibility; stored config and revision |
| `test_failed_episodes_abort_the_experiment_but_keep_partial_results` | 202–213 | failure handling at experiment level |
| `test_committed_results_match_the_committed_code_config_and_report` | 216–222 | stored results belong to this code and config; the report matches the JSON |

| Command | Result |
|---|---|
| `python3 test_research.py` | `ok` (11 tests) |
| `python3 test_simulation.py`, `test_race.py`, `test_tyres_fuel_pits.py`, `test_traffic.py`, `test_weather.py`, `test_race_control.py`, `test_validation.py`, `test_rl.py` | all `ok`: regression for the stable simulator and the V7 environment |
| `python3 -m research.scenario_coverage` | completed twice (§2) |

**Mutation check (manual, not committed).** In a scratch copy, 13 deliberate bugs were introduced one at a time:

- paired difference with the sign flipped;
- unseeded bootstrap;
- wrong bootstrap tail;
- exceptions not captured;
- results reordered;
- strata swapped;
- no equal-budget check;
- no held-out check;
- failed candidates allowed as elites;
- verdict using the wrong CI bound;
- failures not aborting the experiment;
- failed training episodes scored as 0;
- baseline check removed.

The first run missed four (bootstrap tail, result ordering, failed elites, failed episodes scored as 0). The tests were strengthened; all 13 are now caught.

## Experimental artefacts

| Artefact | Meaning |
|---|---|
| `research/results/scenario_coverage.json` | **Measured results**: config, revision, per-episode data, summaries, verdicts |
| `research/results/scenario_coverage.md` | Report rendered from that JSON |
| `research/configs/*.json` | Inputs |

## Deliberately absent

- **Hierarchical RL:** no lower-level decisions exposed (IMPLEMENTATION.md §3).
- **Multi-agent RL:** agents would be independent under the time reward; deferred.
- **Deep RL:** not justified at about 2 s per episode.
- **2026 ERS or active-aero modelling:** not required by the question.
- **Changes to the simulator, the V7 environment or the V6 tooling.**

## Known limitations

See IMPLEMENTATION.md §8–9. In short:

- one policy family;
- a small budget;
- strata defined by env switches;
- the controlled car runs alone;
- the CIs cover race-to-race noise only; run-to-run variation is reported separately;
- placeholder model parameters;
- one track;
- results describe the simulator, not F1.

V8 is the end of the planned roadmap. It is not a claim that the simulator is complete or scientifically validated.
