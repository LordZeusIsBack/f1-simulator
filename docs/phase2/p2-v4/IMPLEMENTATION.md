# P2-V4: Trainable AI driver

Phase 2 milestone 4 of 6. This version adds a reinforcement-learning environment for **driving** decisions (`rl/driver_env.py`), a training and evaluation workflow (`rl/driver_learning.py`), and one small simulator change that makes learning meaningful: **tyre wear now depends on how hard a controlled car is driven**. The strategist's environment (`rl/env.py`) is untouched.

Line numbers are from the P2-V4 commit and may shift; symbol names are the stable reference.

## 1. Scope

**In scope:**
- a driving environment with `reset()` and `step()`, a normalised observation, masked discrete actions, a reward, seeds and diagnostics;
- driving-dependent tyre wear for controlled cars, with `tyre_management` setting how much a driver saves;
- baselines: three fixed styles and the three P2-V2 rule-based drivers;
- tabular Q-learning, plus a seeded experiment (3 training runs, held-out evaluation with paired confidence intervals) whose configuration and results are stored;
- a fix to a P2-V3 bug found while building the environment (§3.2).

**Out of scope:**
- connecting the driver to the strategist (P2-V6);
- several learning drivers racing each other (P2-V5);
- pedal-level (throttle/brake) actions, wet weather, race control and pit stops inside the driving environment.

## 2. Before this version

- **P2-V3:** a car with `CarControl` is moved by pedals and physics. Its `DriverAction` sets a grip share: 1.0 for ATTACK and DEFEND, 0.97 for MAINTAIN_PACE, 0.90 for CONSERVE_TYRES.
- **The missing piece:** tyre wear was `laps × wear_per_lap` for every car. Driving slower therefore cost time and saved nothing. Any learner would conclude "always attack", and that answer is already known without learning.
- **The strategist environment** (`StrategyEnv`, V7/V9): one pit decision per lap, a normalised observation, reward −(race time)/reference lap, and the policy convention `policy(observation, mask) -> int`. The evaluation helpers live in `rl/evaluate.py`, and the CEM tuning in `rl/experiment.py` and `research/`.

## 3. Simulator changes

### 3.1 Driving-dependent tyre wear (controlled cars only)

**The limitation.** `Tyres.wear()` used whole laps, and `Race` aged every car by exactly one lap per lap. A controlled car's driving style could not change its wear, so the P2-V1 definition of `tyre_management` ("how little pace the driver gives up to reduce tyre wear by a given amount") had no mechanism.

**The change:**
- `control.wear_factor(grip_share, tyre_management)` (`control.py:62`) gives the wear per metre relative to driving at the limit:
  ```
  wear_factor = grip_share ^ (WEAR_EXPONENT × (0.5 + tyre_management)),   WEAR_EXPONENT = 8 (placeholder)
  ```
  The exponent is 4 at skill 0, 8 at 0.5 and 12 at 1.

  | Grip share (action) | skill 0 | skill 0.5 | skill 1 |
  |---|---|---|---|
  | 1.00 (ATTACK, DEFEND) | 1.000 | 1.000 | 1.000 |
  | 0.97 (MAINTAIN_PACE) | 0.885 | 0.784 | 0.694 |
  | 0.90 (CONSERVE_TYRES) | 0.656 | 0.430 | 0.282 |

  At the limit every driver wears the same. Below it, a better tyre manager saves more wear for the same loss of pace. That is the trade the master prompt asks for: the skill is worth something only if the driver chooses to drive below the limit.
- `CarControl.load` (`control.py:59`) adds up, over the current lap, the metres driven × `wear_factor` of the action in force. `Race._advance_controlled` adds to it in every sub-step (`race.py:466`, and line 460 for the part up to the line), using the metres actually moved, including when the car is held behind another.
- `Tyres.used` (`tyres.py:35`) is a new optional field: laps' worth of wear at full push. `None` (the default) means "equal to `laps`". `Tyres.wear()` uses `used` when it is set.
- `Race._complete_lap` (`race.py:521`): for a controlled car, `used += load / track length`, then `load = 0`. For every other car nothing changes. Load counts from the start line, as wear does for profile cars.

**Grip still changes once per lap.** The new wear reaches the grip at the line, as for every car. Changing grip in every sub-step would force a new braking envelope in every sub-step, which costs about 0.19 s each.

**Checks:**
- an ATTACK car's tyres reach exactly `used = laps`, the same wear as a profile car;
- uncontrolled cars' `Tyres` are unchanged;
- all V0–V5 recorded results still pass.

### 3.2 Bug fix: DRS let a controlled car brake too late (P2-V3)

While testing the environment, the controlled car clipped its corner limit 9–13 times per 5-lap race from lap 3 on. Clips are sub-steps where the race had to cap its speed.

**Cause.** P2-V3 divided the controller's target speed by the race's time factor, and DRS makes that factor 0.965 on long straights. The target was therefore 3.6 % above the braking envelope, including in the braking zone at the end of the straight. The car braked too late, and the corner cap then removed the excess speed for free. That is a time gain no real car could make, and a reward exploit for a learner.

**Fix** (`race.py:446`): the target is divided by `max(factor, 1.0)`. Pace, dirty air and flags still slow a controlled car, and DRS now has no effect on it, which is what P2-V3's documentation already claimed. Clips in the environment dropped to 0.

**Consequences:**
- the P2-V3 README example changed (README and the note in [P2-V3 IMPLEMENTATION.md §10](../p2-v3/IMPLEMENTATION.md));
- the P2-V3 tests still pass;
- uncontrolled cars are not affected.

## 4. The RL formulation

### 4.1 Episode
`DriverEnv(laps=5, track="Monza", team="McLaren", driver=Driver("Agent"), opponents=3, wear_price=130, dt=0.25, max_steps=None, seed=None, calibration="calibrated")` (`rl/driver_env.py:61`).

- **One episode** is one race of `laps` laps on V9 Monza with V9's calibrated grip (as `StrategyEnv`). Every car is on mediums, with fuel for the race and no pit stops. The race is dry, with no race control.
- **The ego car** (number 1) has `CarControl()`. The `opponents` rivals follow their lap profiles (they are uncontrolled). Traffic is on: dirty air, DRS and the passing rule apply.
- **Scenario, drawn in `reset(seed)`:**
  - each rival driver's `pace` and `racecraft`, uniform 0–1 (rounded to 0.01);
  - the ego car's grid slot.

  `info["scenario"]` records the draw. The agent never observes it.
- **Decisions** are made every `DECISION_DISTANCE` = 250 m (24 per Monza lap). They are spaced in **distance, not time**, so the time a step takes measures the pace of that action. With fixed time steps, every step would cost the same time and the reward would carry no signal until the finish.
- Between decisions the race advances in steps of `dt` = 0.25 s. The controlled car is integrated in 0.02 s sub-steps (P2-V3). A decision is therefore applied at the first race step after the 250 m mark, up to about 25 m late at 90 m/s.
- **Termination:** the ego car finishes (`terminated`). **Truncation:** `max_steps` decisions were made (`truncated`). The rivals' race is not continued after the ego car finishes.

### 4.2 Observation (`Observation`, `rl/driver_env.py:38`)
Ten floats, built from the P2-V2 `driving.observe` (what a driver may know) and normalised:

| Field | Meaning | Unit before scaling | Normalisation | Range |
|---|---|---|---|---|
| `progress` | distance covered / race distance | m | ÷ race distance | 0–1 |
| `speed` | own speed now | m/s | ÷ `SPEED_SCALE` (100), capped | 0–1 |
| `on_straight` | on a straight (where passes start) | | 0/1 | 0–1 |
| `gap_ahead` | time to the car ahead | s | ÷ `GAP_SCALE` (3), capped; 1 if none | 0–1 |
| `closing` | own speed − ahead's speed at this spot | m/s | ÷ `CLOSING_SCALE` (10), clipped; 0 if none | −1 to 1 |
| `gap_behind` | time of the car behind | s | ÷ 3, capped; 1 if none | 0–1 |
| `held_up` | the passing rule is holding this car behind | | 0/1 (`car.held_by`) | 0–1 |
| `drs` | DRS usable this lap | | 0/1 | 0–1 |
| `tyre_wear` | wear including this lap so far | | as is | 0–1 |
| `position` | (position − 1) / (cars − 1) | | | 0–1 |

**Knowledge boundaries.** The observation never contains:
- the rivals' skills, the scenario draw or the seed;
- `wear_price`;
- the driver's own skill values.

**Where the skills go** (prompt requirement 5). The agent learns to drive **one fixed driver**, given as `DriverEnv(driver=...)`. The skills shape how the environment responds:
- `pace` slows the controlled car's target;
- `attack` and `defence` enter the passing rule;
- `tyre_management` sets `wear_factor`.

Within an environment they are constant, so putting them in the observation would add inputs with no information. If a later milestone wants one policy for many drivers, the skills would then have to become observations.

### 4.3 Actions
`ACTIONS = tuple(DriverAction)`: 0 MAINTAIN_PACE, 1 ATTACK, 2 DEFEND, 3 CONSERVE_TYRES. These are the tactical actions the P2-V3 controller already executes. Pedal-level actions were not added: 24 decisions per lap is already the right timescale for "how hard to drive", while pedal decisions every 0.02 s would make episodes 200 times longer to learn from.

`action_mask()` uses P2-V2's `available_actions`:
- ATTACK needs a car ahead;
- DEFEND needs a car behind;
- MAINTAIN_PACE and CONSERVE_TYRES are always allowed.

`step()` rejects anything else with `ValueError`. **Consequence:** a car with nobody ahead or behind cannot use more than 97 % of the grip. This is P2-V2's definition of ATTACK and DEFEND, kept on purpose.

### 4.4 Reward
For each step, from distance d₀ at time t₀ to distance d₁ at time t₁ (the finish time on the last step):

```
time_lost = (t₁ − t₀) − (T_ref(d₁) − T_ref(d₀))          s
wear_cost = wear_price × (wear(t₁) − wear(t₀))           s-equivalent
reward    = −(time_lost + wear_cost)
```

- **`T_ref`** is the ideal lap of the ego car: a `LapProfile` at new-tyre grip with the start fuel. Subtracting it does not change which policy is best, because over the fixed race distance its total is a constant. It does remove the large variation between steps on straights and in chicanes, so a step's reward measures only what the action changed.
- **`wear_price`** (seconds per unit of wear) is the value of tyre life **after** this race segment. Within the episode, worn tyres already cost time through lower grip. With `wear_price = 0`, the only objective is time.
- The default 130 s is a placeholder, chosen so that no fixed driving style is best on its own. On 12 probe seeds (500–511, used in neither training nor evaluation):

  | Style | Mean cost |
  |---|---|
  | always maintain | 20.99 s |
  | always push | 21.15 s |
  | always conserve | 21.34 s |
  | best hand-written state rule (conserve when held up, attack when close and faster, else maintain) | 20.84 s |

  At 100 s, "always push" wins outright and leaves little to learn.
- In P2-V6 the strategist is the natural owner of this price.

**Return over an episode** = −(finish time − ideal time over the distance + `wear_price` × wear added).

**Terms deliberately left out:**
- **Track limits / clips:** no action can exceed the grip, so clips are not a driver choice (and since §3.2 they are 0). A penalty would add noise without shaping a decision. `info["clipped"]` reports them.
- **Position or passes:** the objective is time, and position is a consequence of it. Rewarding passes directly would encourage attacking that does not save time.
- **Raw speed:** prompt requirement 7. Speed is rewarded only through time over a fixed distance.

### 4.5 Info (diagnostics)
Every `reset` and `step` returns:
- `lap`, `distance`, `race_time`, `finish_time`, `position`;
- `passes` (made by the ego car), `passed_by`, `tyre_wear`, `clipped`;
- `time_lost`, `wear_cost`: the two reward parts of the last step;
- `action_mask`;
- `driver_observation`: the P2-V2 `DriverObservation`, so the P2-V2 rule-based policies can drive in this environment;
- `scenario`.

### 4.6 Seeds
- `reset(seed=s)` replaces the environment's random generator with `random.Random(s)`, so the scenario and therefore the whole episode are reproducible. Everything after the draw is deterministic.
- `DriverEnv(seed=...)` seeds the generator for `reset()` calls without a seed.

## 5. Policies and the learner (`rl/driver_learning.py`)

**Interface.** A driving policy here is `policy(observation, info) -> action index`. This is the strategist's convention, with `info` in place of the mask, because the P2-V2 adapters need `info["driver_observation"]` and every policy can read `info["action_mask"]`.

**Baselines** (`baselines(driver)`, line 64):

| Name | Rule |
|---|---|
| `maintain` | always MAINTAIN_PACE (0.97) |
| `push` | ATTACK if allowed, else DEFEND if allowed, else MAINTAIN_PACE: as close to the limit as the rules allow |
| `conserve` | always CONSERVE_TYRES (0.90) |
| `rule conservative`, `rule balanced`, `rule aggressive` | P2-V2 `RuleBasedDriver`s through the `RuleBased` adapter (line 54); unchanged |

### 5.1 Algorithm: tabular Q-learning

**Why this algorithm.** The problem has:
- 4 masked discrete actions;
- a reward at every step that mostly reflects the last action (time and wear over the next 250 m);
- delayed effects only through traffic (passing now, or staying stuck).

Off-policy temporal-difference learning assigns credit per step, which suits this. A table needs no dependencies (the project has none) and its result can be read state by state.

**Alternatives considered:**
- **Cross-entropy search over a parametric rule** (as V7/V8 did for the strategist) scores only whole episodes. A 5-lap episode has 116 decisions, so the per-decision signal would be buried in the scenario noise.
- **DQN or policy gradients** would need numpy or torch for a 10-number observation. That is a large dependency stack with no justification here.

**State** (`state()`, line 71). The learner discretises the observation into 3 × 3 × 2 × 2 × 2 × 2 = 144 states:
- car ahead: none or ≥ 1.5 s, 0.5–1.5 s, < 0.5 s;
- closing speed: not faster (or no near car), up to 2 m/s, more than 2 m/s;
- held up;
- car behind within 1 s;
- on a straight;
- DRS.

Wear, progress and position are left out: with a linear wear price the marginal value of wear does not depend on the wear level, and keeping the table small makes the training budget sufficient.

**Update** (`QLearner.update`, line 104):

```
Q(s, a) ← Q(s, a) + α (r + γ max_{a' allowed in s'} Q(s', a') − Q(s, a))
```

The bootstrap term is dropped at termination. Settings:
- α = 0.1;
- γ = 0.9 per decision, an effective horizon of about 10 decisions or 2.5 km, which covers a passing manoeuvre;
- ε-greedy exploration among allowed actions, ε falling linearly from 0.3 to 0.02 over a run.

Unvisited pairs start at 0, which is optimistic because rewards are ≤ 0, so every allowed action gets tried. Greedy play (evaluation) considers only actions tried in that state, and falls back to MAINTAIN_PACE in a state never seen.

### 5.2 Training and evaluation procedure (`experiment`, line 183)

| Setting | Value |
|---|---|
| Environment | `laps=5, track="Monza", team="McLaren", opponents=3, dt=0.25`, default driver (all skills 0.5) |
| Wear prices | **130** (main) and **0** (control) |
| Training runs | 3 per wear price, 300 episodes each. Run r trains on seeds 1000·r + 0..299 and uses learner seed r |
| Evaluation | 30 held-out seeds 10000–10029, the same for every policy; never used in training or probing |
| Comparison | paired per seed against the best baseline: cost = −return; 95 % percentile bootstrap, 10,000 resamples, seed 0 (`research.stats.paired`, reused from V8) |
| Parallelism | 7 processes; results do not depend on it (each job is seeded) |
| Stored | `rl/reports/driver_experiment.json` (settings, git revision, every training return, every learned table, every evaluation episode) and `rl/reports/driver_experiment.md` (generated report) |

**Why a control condition.** With `wear_price = 0`, "push" is the best possible policy (time is the only cost and nothing is faster than the limit), so it shows whether the learner can find a known optimum. A learner that fails there would not be trusted at 130 either.

## 6. Results

**What was run.** `python3 -m rl.driver_learning` with the settings in §5.2, on 2026-10-16/17: 66 min 45 s on 7 processes, alongside the V8 re-run.
- **Training:** per wear price, 3 runs × 300 episodes, about 35,000 decisions per run. Seeds 0–299, 1000–1299 and 2000–2299; learner seeds 0, 1, 2.
- **Evaluation:** 9 policies × 30 held-out seeds (10000–10029) × 2 wear prices = 540 episodes.
- **Stored:** every number below is in `rl/reports/driver_experiment.json`, and the full table is in `rl/reports/driver_experiment.md`.

Cost = −return = seconds lost against the ideal lap + wear price × wear added, per 5-lap race; lower is better. The difference column is paired per seed against the best baseline, with a 95 % bootstrap interval.

**Main condition, wear price 130 s.** Best baseline: `rule conservative`.

| Policy | Mean cost (s) | Time lost (s) | Wear cost (s) | vs rule conservative (s) | Better / worse seeds |
|---|---|---|---|---|---|
| maintain | 20.34 | 5.06 | 15.28 | +0.85 [+0.49, +1.23] | 9 / 21 |
| push | 20.38 | 0.88 | 19.50 | +0.90 [+0.68, +1.14] | 1 / 29 |
| conserve | 21.37 | 12.98 | 8.39 | +1.88 [+1.42, +2.28] | 5 / 25 |
| rule conservative | **19.49** | 3.75 | 15.74 | 0 | |
| rule balanced | 19.58 | 3.42 | 16.16 | +0.09 [−0.07, +0.25] | 11 / 19 |
| rule aggressive | 19.54 | 2.89 | 16.64 | +0.05 [−0.21, +0.35] | 13 / 17 |
| Q-learning run 0 | 20.60 | 3.63 | 16.97 | +1.11 [+0.81, +1.42] | 5 / 25 |
| Q-learning run 1 | 20.83 | 4.64 | 16.18 | +1.34 [+0.99, +1.67] | 2 / 28 |
| Q-learning run 2 | 20.23 | 1.07 | 19.16 | +0.74 [+0.58, +0.90] | 0 / 30 |

**Control condition, wear price 0 s.** Best baseline: `push`, which is the known optimum (§5.2).

| Policy | Mean cost (s) | vs push (s) | Better / worse seeds |
|---|---|---|---|
| push | **0.88** | 0 | |
| rule aggressive (best of the others) | 2.89 | +2.01 [+1.80, +2.21] | 0 / 30 |
| Q-learning run 0 | 0.88 | −0.00 [−0.23, +0.19] | 2 / 3 |
| Q-learning run 1 | 1.07 | +0.19 [−0.00, +0.46] | 1 / 4 |
| Q-learning run 2 | 1.63 | +0.74 [+0.37, +1.18] | 1 / 20 |

No policy clipped a corner limit in any evaluation episode.

**Findings:**
1. **The learned driver does not beat the baseline.** At wear price 130, all three Q-learning runs are worse than the best rule-based driver, by 0.74–1.34 s per race. Every interval lies entirely above 0. They are also no better than the fixed styles (20.23–20.83 s against 20.34–20.38 s).
2. **Rising training reward did not mean a good policy.** The mean training return (with exploration) rose in every run, for example from −22.06 to −20.90 in run 2, but the greedy policies lost to the baseline on held-out races.
3. **The runs disagree with each other.** Run 2 drives almost always at the limit (DEFEND on 101 of 116 decisions). Runs 0 and 1 mix MAINTAIN_PACE and DEFEND, and choose CONSERVE_TYRES 13–18 times a race, which no baseline does. The same state often gets a different greedy action in different runs.
4. **Probable cause: the main condition has almost no signal per decision.** The wear price was chosen so that no fixed style is best (§4.4), and on the evaluation seeds it does that: maintain 20.34 s, push 20.38 s. Per 250 m, pushing saves about 4.18 / 116 = 0.036 s and costs about (19.50 − 15.28) / 116 = 0.036 s of wear. In most states the true Q values of these actions are therefore almost equal, while the reward of a single step varies more than that because of traffic. With a constant α = 0.1, the greedy choice between them is close to a coin toss. The rule-based drivers gain about 0.85 s over the fixed styles with rare, situational choices, such as attacking only when close and faster and defending only when someone is close behind, whose effects play out over several steps through traffic. The learner did not find these.
5. **The learner finds a clear optimum, but not reliably.** At wear price 0, run 0 matches `push` and run 1 nearly does, but run 2 is 0.74 s worse. All three beat every other baseline there by at least 1.26 s.

**Conclusion.** P2-V4 delivers a working, tested and reproducible environment and training workflow. **The trained policy is not an improvement over the rule-based baseline.** Directions that might change this were not tried, because P2-V4 stops here:
- a larger budget or a decaying α;
- a state that includes the position on the lap;
- averaging several runs;
- function approximation.

`rule conservative` remains the driver baseline to beat.

## 7. Assumptions, limitations, sim-to-reality

- **The wear model is a placeholder.** Both the power law and `WEAR_EXPONENT` = 8 are assumptions, not tyre data. Wear follows the *planned* grip share, not the measured tyre load: a car held up at ATTACK wears as if it were pushing.
- **The wear price is a placeholder** chosen to balance the styles (§4.4). The experiment's conclusions hold for this price, this track and this field only.
- **The environment is narrow:** one track, 5 laps, mediums, dry, no race control, 3 profile-driven rivals that do not react, and one fixed driver. A policy learned here has not been tested elsewhere.
- **The longitudinal model limits the actions** (P2-V3). There is no racing line, DEFEND drives like ATTACK, and DRS has no effect on the controlled car.
- **The action mask caps solo pace at 97 % of the grip**, because ATTACK and DEFEND need a rival nearby (P2-V2 rule).
- **Observations are exact and instantaneous.** The state discretisation is hand-designed and loses information, for example position on the lap and how far behind the car ahead is beyond 1.5 s.
- **The learning budget is small:** 300 episodes, about 35,000 decisions per run, and 3 runs. Variability across runs is reported, but 3 runs cannot characterise it well.
- **Sim-to-reality:** nothing here transfers to a real car. The physics is the simplified V0 model, the grip is a calibrated *effective* value (V6/V9), and tyre behaviour, temperatures, and driver feel are not modelled. A result describes this simulator.

## 8. Why this is a suitable foundation for P2-V5

- The environment, the `policy(observation, info)` interface and `run_episode` work for any policy: learned tables, the P2-V2 rules and fixed styles.
- P2-V5 can place several controlled cars with different policies in one race. The race already supports any number of `CarControl` cars, and the experiment code already pairs seeds and computes bootstrap intervals.
- `wear_price` is the hook through which the strategist can steer the driver in P2-V6.
