# V8: Advanced strategy research (implementation)

## 1. Objective and scope

V8 runs **one controlled research experiment** on top of the V7 environment. It changes neither the simulator (V0–V5), nor the validation tooling (V6), nor the RL environment (V7). New code lives in `research/`.

This is the last planned roadmap version. It is **not** a claim that the simulator is complete or scientifically validated (see V6).

## 2. Audit of the V7 setup

| Part | What V7 provides | Weakness found |
|---|---|---|
| Environment | One controlled car; a pit call per lap, 300 m before the line; 6 masked actions; seeded scenarios (VSC/SC 50 %, rain 25 %) | **About 2 s per 53-lap episode**: small sample budgets. Opponents use fixed plans. |
| Observation | 19 normalised floats, a restricted view | Tyre wear is exact (idealised); no forecast |
| Reward | −(race time + penalties) ÷ reference lap, dense, exact sum | Rewards time, not position; it cannot express "beat a rival" |
| Baselines | stay out, fixed one-stop, hand-set rule (4 thresholds), random | The hand-set rule was the strongest, beating the fixed one-stop on 18 of 20 held-out races |
| Learning | CEM over the rule's 4 thresholds on **3** training races | **No improvement** on held-out races. **None** of the 3 training races had a VSC or SC, so 2 of the 4 thresholds were never exercised. |
| Evaluation tooling | paired comparison on shared seeds; mean, std, better/worse | No confidence intervals, a single run (no variation across runs), no record of the code version, no handling of failed episodes, serial only |

## 3. Research question

**Does the scenario composition of the training races decide whether tuning the rule's thresholds beats the hand-set rule on held-out races?**

- **Hypothesis H1:** training on a *stratified* set (2 quiet, 2 VSC/SC, 2 wet races) gives tuned policies that beat the hand-set rule on held-out races, while training on the *same number* of randomly drawn races does not.
- **Null result:** neither design beats the hand-set rule reliably.

**Decision rule, fixed before running** (it is in the config and is applied by code):

> A design **helps** if, in at least 2 of its 3 CEM runs, the 95 % bootstrap confidence interval of the paired race-time difference (tuned − hand-set, 40 held-out races) lies entirely below 0.

### Why not hierarchical or multi-agent RL

- **Hierarchical:** the simulator exposes **no lower-level decisions**. Driving follows precomputed lap profiles, and a driver's pace is a fixed attribute. A low-level controller would need a new driving-control model, which is a rewrite of the physics core and outside this version's brief. The only decision level the environment supports is strategy.
- **Multi-agent:** technically possible, because the V2 strategy hook works per car. It is not meaningful yet:
  1. The reward is each car's own time. Without traffic, agents do not affect each other, so it is just N single-agent problems.
  2. With traffic, every episode costs about 2 s × N, and V3's step-size sensitivity would add noise.
  3. V7 showed that at this budget even **one** tuned agent does not beat a hand rule.

  A smaller controlled experiment is the more informative next step.

## 4. Experiment design (`research/configs/scenario_coverage.json`)

| Element | Setting |
|---|---|
| Race | `StrategyEnv(laps=53, team="McLaren", pit_loss=22.0)`, controlled car alone |
| Policy family | `RuleBased(wear_limit, neutral_from, neutral_to, final_call)` (V7) |
| Training design **random** | 6 races from the default distribution (VSC/SC 0.5, rain 0.25), seeds 0–5 |
| Training design **stratified** | 2 races with no events (seeds 0–1), 2 with VSC/SC forced (chance 1, seeds 2–3), 2 with rain forced (chance 1, seeds 4–5) |
| Equal budget | 6 training episodes per candidate in both designs (checked by the config validator) |
| Optimiser | Cross-entropy method: start at the hand-set thresholds, 4 iterations × population 8, 2 elites, bounds as in V7 |
| Repetitions | **3 runs per design**: CEM seed r = 0, 1, 2, and **training seeds shifted by r × 7919**, so each run trains on different races |
| Evaluation | 40 held-out races (seeds 1000–1039) from the default distribution, the same for every policy (paired) |
| Policies evaluated | hand-set `rule-based`, `fixed one-stop`, and the 6 tuned policies |
| Sensitivity check | the same 8 policies re-evaluated with **`pit_loss = 25.62` s**, the Monza value measured in V6, without retraining |
| Statistics | paired differences; 2000-resample percentile bootstrap, seed 0, 95 %; better/worse/tie counts; breakdown by race type |
| Failure policy | `max_failed_episodes = 0`; any failed episode marks the experiment aborted |

## 5. Metrics

- **Race time:** finish time plus penalties, in s; lower is better.
- **Paired difference** on each held-out seed: tuned − hand-set. We report its mean, std and 95 % bootstrap CI, and the better/worse/tie counts.
- **By stratum:** the mean paired difference separately for quiet, neutralised (VSC/SC, no rain) and wet races, as classified from each seed's scenario.
- **Across runs:** the mean and std of the 3 runs' mean differences. This shows how much the *outcome of tuning* varies, not just race-to-race noise.
- **Verdict:** the decision rule above, computed by `verdict()`.

## 6. Infrastructure added (`research/`)

| Module | Role |
|---|---|
| `config.py` | Strict JSON config validation (`ConfigError`): unknown or missing keys, types, ranges, equal training budgets, held-out seeds after the per-run shift, valid bounds, known baselines |
| `runner.py` | `EpisodeSpec` (env settings, seed, policy) → `run_spec` runs one episode through the **V7 `run_episode`**; failures come back as `{"error": ...}` instead of raising. `run_specs` keeps input order with any number of processes (fork pool). `code_revision()`/`code_digest()` record git HEAD, whether the tree was dirty, and a sha256 of every non-test `.py` file. |
| `stats.py` | `summary`, seeded `bootstrap_ci`, `paired` |
| `cem.py` | Batched CEM, so a whole population runs in parallel; failed candidates (score −∞) are counted and never become elites |
| `scenario_coverage.py` | The experiment: train → evaluate (main + sensitivity) → aggregate → verdict → store JSON and a Markdown report |

**Results are tied to code:**

- `research/results/scenario_coverage.json` stores the full config, git HEAD, the dirty flag and the code digest.
- A test checks that the stored digest equals the digest of the code being committed. If any simulator, environment or research `.py` file changes, the test fails until the experiment is re-run.
- The results were produced before the V8 commit existed, so `git_head` is V7's commit and `dirty` is true. **The digest is the binding identifier.**

## 7. Results

Full report: [`research/results/scenario_coverage.md`](../../../research/results/scenario_coverage.md); per-episode data is in the `.json`.

- The experiment ran to completion with **0 failed episodes**, 7 processes, about 30.5 minutes of wall time.
- It ran twice, with identical training and evaluation results. The second run followed a report-formatting fix (CHANGELOG).

### 7.1 Training (gains are on that run's own 6 training races)

| Design | Run | Tuned thresholds (wear, neutral window, final call) | Training gain over hand-set |
|---|---|---|---|
| random | 0 | 0.671, 0.316–0.598, 0.902 | 4.28 s per race |
| random | 1 | 0.768, 0.671–0.913, 0.774 | 0.40 s |
| random | 2 | 0.704, 0.324–0.722, 0.874 | 0.06 s |
| stratified | 0 | 0.646, 0.601–1.000, 0.764 | 0.55 s |
| stratified | 1 | 0.75, 0.30–0.85, 0.85 (hand-set kept) | 0.00 s |
| stratified | 2 | 0.704, 0.324–0.722, 0.874 | 0.08 s |

Random run 2 and stratified run 2 returned **the same** thresholds. Both used CEM seed 2, so they drew the same first-iteration candidates, and the same candidate won in both. At this budget, which candidate wins depends more on the optimiser's random draws than on the training set.

### 7.2 Held-out evaluation (40 races, pit_loss 22 s): paired difference against hand-set `rule-based`

| Policy | Mean ± std (s) | 95 % bootstrap CI (s) | Better / worse / tie | Quiet / neutralised / wet (mean, s) |
|---|---|---|---|---|
| fixed one-stop | +5.01 ± 15.36 | [+0.96, +10.30] | 4 / 36 / 0 | +0.3 / +0.3 / **+23.8** |
| tuned random run 0 | +1.21 ± 5.79 | [−0.10, +3.45] | 8 / 27 / 5 | +0.2 / +1.0 / +3.5 |
| tuned random run 1 | +0.43 ± 1.13 | [+0.16, +0.81] | 1 / 34 / 5 | +0.1 / +0.7 / +0.5 |
| tuned random run 2 | +0.80 ± 3.82 | [−0.10, +2.21] | 7 / 27 / 6 | +0.0 / +0.8 / +2.2 |
| tuned stratified run 0 | +1.35 ± 5.65 | [+0.04, +3.54] | 8 / 28 / 4 | +0.4 / +1.3 / +3.0 |
| tuned stratified run 1 | +0.00 | [0, 0] | 0 / 0 / 40 | identical to hand-set |
| tuned stratified run 2 | +0.80 ± 3.82 | [−0.10, +2.21] | 7 / 27 / 6 | +0.0 / +0.8 / +2.2 |

There were 14 quiet races, 18 neutralised and 8 wet. Hand-set rule-based averaged 5193.6 ± 128.9 s.

**Decision rule:**

| Design | Runs with CI below 0 | Runs with CI above 0 | Mean of run means | Helps? |
|---|---|---|---|---|
| random | 0 / 3 | 1 / 3 | +0.81 ± 0.39 s | **no** |
| stratified | 0 / 3 | 1 / 3 | +0.72 ± 0.68 s | **no** |

### 7.3 Sensitivity: pit loss 25.62 s (V6 measured), same policies, no retraining

- The verdict is the same for both designs: no run has a CI below 0. The run means are +0.95 s (random) and +0.86 s (stratified).
- **Fixed one-stop vs hand-set:** +2.64 ± 13.65 s, CI [−0.92, +7.23]. The flexible rule's advantage is about **half** what it is at 22 s, and its CI now includes 0. In wet races it drops from +23.8 to +12.1 s, because the rule's extra weather stops cost more.

### 7.4 Conclusions

**Supported by these results (within this simulator):**

1. **H1 is not supported.** Tuning on a stratified training set did **not** beat the hand-set rule; neither did tuning on random races. No tuned policy had a CI below 0. Two (random run 1, stratified run 0) were reliably *worse* by a fraction of a second per race.
2. **The tuning overfits.** Random run 0 gained 4.3 s per race on its training races and lost 1.2 s per race on held-out races. The other runs found training gains of 0.6 s or less.
3. **The hand-set thresholds sit in a flat region for this model.** No tuned variant moved the held-out mean by more than 1.4 s per race (≈ 0.03 % of race time). The race-to-race spread is about ±130 s, driven by the scenario. Where differences exist, they come mostly from wet races.
4. **Reacting to weather and flags matters more than tuning thresholds.** The rule beats a fixed one-stop by 5.0 s (CI above 0 at pit_loss 22 s).
5. **A V6 parameter error can change a conclusion.** At the measured pit loss of 25.62 s, the rule's advantage over the fixed one-stop is no longer statistically clear.

**Not supported or not claimed:**

- that the hand-set rule is optimal;
- that stratification never helps at larger budgets or with other policy families;
- anything about real F1 strategy.

**Inconclusive:**

- whether the small *negative* effect of tuning is real for every design. Only 2 of 6 runs had CIs above 0, and the run-to-run variation (std 0.4–0.7 s) is the same size as the effect.

## 8. How V6's limitations may influence these results

| V6 finding | Possible influence |
|---|---|
| Model pit loss of 22 s is about 3.6 s below Monza's measured 25.6 s | Stopping looks cheaper than in reality, which favours policies that stop more. Tested directly by the sensitivity evaluation at 25.62 s. |
| Tyre, fuel, weather and race-control effects are unvalidated placeholders | The tuned thresholds exploit **this model's** degradation and wet-grip curves. Their values are not transferable to real F1. |
| Race-vs-qualifying pace is under-modelled (degradation too mild) | Long stints are under-penalised, which pushes `wear_limit` upwards |
| Lap times are about 19 % slow; only Monza is modelled | Absolute race times are not meaningful; only differences within the model are |

## 9. Assumptions and limitations

1. **One policy family.** The question is about tuning 4 thresholds of a hand-written rule, not about general RL.
2. **Small budgets:** 6 training races per candidate, 33 candidates per run, 3 runs per design, 40 evaluation races. Effects smaller than about a second may not be detectable.
3. **Strata defined by the env's own event switches** (VSC/SC on or off, rain on or off). The random design still contains them, at their natural rates.
4. **The controlled car runs alone.** Traffic and rivals don't matter here, and the reward is time.
5. **The bootstrap CI treats the 40 races as independent and identically distributed.** It does not include variation between training runs; that is reported separately across the 3 runs.
6. **The results are about the simulator, not Formula 1** (§8).
