# V7: Reinforcement-learning environment (implementation)

> **Later change (V9):** the environment now uses the calibrated grip, any circuit, and hidden random pit loss, fuel burn and tyre wear. The experiment was re-run; see [V9 IMPLEMENTATION.md §8.1](../v9/IMPLEMENTATION.md#8-results). The results below are V7's.

## 1. Objective and scope

V7 turns the simulator into an **environment**: an agent observes a race, makes pit-stop decisions, gets rewards and can be trained over repeated, reproducible episodes. V7 provides:

- `StrategyEnv` with `reset()` and `step()`, Gymnasium-style signatures, no dependency (`rl/env.py`);
- a documented observation space (19 normalised numbers), action space (6 actions, with a mask) and reward;
- four non-learning **baselines** (`rl/policies.py`);
- an **evaluation** harness that runs every policy on the same seeded episodes and reports the spread (`rl/evaluate.py`);
- a **minimal learning experiment**: a cross-entropy-method search over the rule-based policy's four thresholds, evaluated on held-out seeds (`rl/experiment.py`).

It is **not** a competitive strategist, and not deep RL. The simulator (V0–V5) and the validation tooling (V6) are unchanged.

## 2. Dependencies

`pyproject.toml` has no dependencies, and neither `gymnasium` nor `numpy` is installed. V7 therefore adds **none**:

- **Environment.** The interface is 19 floats in, one integer out. That needs no array library. The signatures follow Gymnasium (`reset(seed) → (obs, info)`, `step(a) → (obs, reward, terminated, truncated, info)`), so a thin `gymnasium.Env` wrapper can be added later if an RL library is wanted.
- **Learning.** One episode takes about 2 s, because the simulator recomputes one physics lap per car per lap (V2). Sample-hungry methods (DQN, PPO) would need tens of thousands of episodes, which is impractical here. A cross-entropy search over 4 parameters needs about 75 episodes and is about 60 lines of standard library. A big framework would add weight with no benefit at this sample budget.

## 3. The problem formulation

### 3.1 Episode

- **One race at Monza:** `laps` laps (default 53), with the V2–V5 models: fuel, wear, pit loss, weather, race control and the two-compound rule.
- **The agent controls one car** (`team`, default McLaren). It controls only that car's pit stops and tyre choices; the simulator drives the car.
- **Opponents** (0–3, default 0) drive fixed one-stop plans that react to rain. With opponents, traffic rules apply (V3).

### 3.2 Decision points ("when actions are accepted")

There are **`laps` decisions** per episode, one per lap. Each comes when the controlled car is **`DECISION_DISTANCE` = 300 m before the line**, the "box or stay out" call before pit entry. That distance is a model assumption.

- `reset()` runs the race from the grid to the first call, about 89.5 s at Monza.
- Each action decides what happens **at the line just ahead**:

| `step(action)` | Effect |
|---|---|
| 0, stay out | No stop at this line |
| 1–5, pit for X | Stop at this line and fit a new set of X (V2 `PitStop`, cost `pit_loss`) |

`step()` then runs the race in `dt` steps (default 0.5 s): across the line, through any stop, and on to the next call, 300 m before the following line. It stops early if the car finishes. Then it returns the next observation.

**Why 300 m before the line, and not just after it?** A first version decided just after each crossing, for the end of the *next* lap. The CODE_FLOW trace showed the problem. A Safety Car that starts mid-lap ends exactly when the leader crosses the line (V5), so for a car running alone it was **never visible** at a decision. Calling before the line makes mid-lap flags and weather visible and lets the agent act on them at once. It also means the stop's cost lands in the same step as the decision.

### 3.3 Action space

`Discrete(6)`: `ACTIONS = ("stay out", "pit for soft", "pit for medium", "pit for hard", "pit for intermediate", "pit for wet")`.

The **action mask** is `info["action_mask"]`, a tuple of 6 booleans:

- "stay out" is always allowed;
- pit actions are allowed unless the lap being driven is the **last** one, because a stop there would happen as the car takes the flag. The compound must also be in the race's table, which is always true with the default table.

`step()` raises `ValueError` if the action:

- is not an `int` (bool, float and str are rejected);
- is outside 0–5;
- is masked.

`step()` raises `RuntimeError` if it is called before `reset()` or after the episode has ended.

Deliberately excluded, to keep the space small:

- fuel and refuelling: the start fuel is fixed at `laps × 1.9 kg`;
- driver pace modes;
- multi-lap plans.

### 3.4 Observation space (restricted view)

`Observation` is a `NamedTuple` of 19 floats, all in [0, 1]. It is both a vector, with fixed order, and named fields.

| # | Field | Meaning, unit before scaling | Scaling |
|---|---|---|---|
| 0 | `progress` | laps completed | ÷ race laps |
| 1–5 | `soft`, `medium`, `hard`, `intermediate`, `wet` | compound now fitted | one-hot |
| 6 | `tyre_wear` | V2 wear of the fitted set (0–1) | as is |
| 7 | `fuel` | kg on board | ÷ 110 kg |
| 8 | `stops` | stops made | ÷ 3, capped at 1 |
| 9 | `two_compounds` | V5 rule met (two dry compounds, or any wet tyre) | 0 or 1 |
| 10–13 | `green`, `yellow`, `vsc`, `safety_car` | race-control flag now | one-hot |
| 14 | `wetness` | track wetness now (0–1) | as is |
| 15 | `rain` | mm/h now | ÷ 10, capped at 1 |
| 16 | `position` | race position | (pos − 1) ÷ (cars − 1); 0 when alone |
| 17 | `gap_ahead` | interval to the car ahead, s | ÷ 30, capped at 1; 1 if nobody is ahead |
| 18 | `gap_behind` | interval of the car behind, s | ÷ 30, capped at 1; 1 if nobody is behind |

**What the agent is not told** (a restricted view):

- the scenario: when or whether a VSC, SC or rain will come, how long it will last, how heavy the rain;
- the opponents' plans and tyres;
- physics parameters, lap profiles and the rest of the simulator state.

**What is idealised:**

- `tyre_wear` is the model's exact value. A real strategist would only estimate it. This is a deliberate simplification.
- Weather is the current value only: there is no forecast.

### 3.5 Reward

```
r_k = −(t_k − t_{k−1}) / T_ref
```

- `t_k` is the race time at the k-th call, with `t_0 = 0`. The first step therefore also covers the run from the grid to the first call. On the final step, `t_k` is replaced by **finish time + penalties**.
- `T_ref` is the controlled car's V0 flying lap, used only as a scale. For the McLaren it is 93.998 s, so a lap is worth about −1.

Therefore

```
Σ r_k = −(finish_time + penalty_time) / T_ref
```

exactly. **Maximising reward means minimising one's own race time including penalties.**

- **Shaping.** No extra terms. The only "penalties" are the race's own rules: the 30 s two-compound penalty (on by default) and the pit loss.
- **Timing.** A stop's stationary time lands in the **same** step as the call that ordered it, because the step runs through the line and the stop to the next call. A test checks this.
- **Direction tests:**
  - an unnecessary extra stop lowers the total reward;
  - breaking the two-compound rule lowers it by exactly 30 s ÷ `T_ref`;
  - the sum equals −(time + penalties) ÷ `T_ref`.
- **What it does not reward:** finishing position. With opponents, position and time can disagree, for example when giving up a place saves time. Time was chosen because it is dense and cannot be gamed by the agent. A position-based reward is a V8 question.
- **Possible misuse checked:**
  - stopping every lap costs time;
  - truncation is imposed from outside, so there is no reward for ending early;
  - invalid actions raise instead of being silently mapped to something else.

### 3.6 Termination and truncation

| | When | Meaning |
|---|---|---|
| `terminated` | the controlled car takes the flag | a natural end: the reward sum is complete |
| `truncated` | `max_steps` decisions made before the finish (default `None`, so never) | an external cut-off: `finish_time` is `None`, the return is partial |

After either one, `reset()` must be called.

### 3.7 Randomness and seeding

Each `reset()` draws a **scenario** from the environment's random generator:

| Event | Probability | Drawn values |
|---|---|---|
| VSC or SC (50/50) | `neutralisation_chance` = 0.5 | start uniform over 15–85 % of the expected race length; duration 60–150 s (for the SC this is the minimum, V5) |
| Rain shower | `rain_chance` = 0.25 | start 10–70 %; 300–900 s long; 2–10 mm/h; 60 s ramps up and down |
| Air temperature | always | 18–32 °C |
| Grid slot | with opponents | shuffled |

- `reset(seed=s)` re-seeds the generator, so the same seed gives the same scenario and, because the simulator is deterministic, the same episode.
- `reset()` without a seed continues the generator: an environment built with `seed=s` replays the same sequence of episodes.

### 3.8 Coupling to the simulator

`rl/env.py` is an adapter that uses only the simulator's public surface:

- **Construction:** `Race`, `RaceCar`, `RaceControl`, `Incident`, `Weather`, `WeatherPoint`, `Strategy`, `PitStop`.
- **Driving:** `Race.step`, `standings`, `car_ahead`, `interval`, `pit_events`, `race_control.flag`, `weather.conditions`, `compounds`.
- **Car state:** `laps`, `tyres`, `fuel`, `finish_time`, `penalty_time`.
- **Scale:** `simulate_lap`.

The controlled car's decisions enter through the **V2 strategy hook**. `_AgentPlan` is a duck-typed `Strategy` whose `stop_after(lap, ...)` returns the agent's pending `PitStop`. No simulator code was changed for V7.

**Policies see only `Observation` and the mask**, never the environment or the simulator.

## 4. Baselines (`rl/policies.py`)

| Policy | Rule |
|---|---|
| `stay_out` | Never pits. Breaks the two-compound rule: the floor. |
| `FixedOneStop(at=0.5, compound=HARD)` | One stop for hards at the first decision at or after half distance; ignores weather and flags |
| `RuleBased(wear_limit=0.75, neutral_from=0.3, neutral_to=0.85, final_call=0.85)` | In this order: (1) the right tyres for the wetness (inters ≥ 0.40, wets ≥ 0.68; back to mediums below 0.30); (2) a cheap first stop under VSC or SC between `neutral_from` and `neutral_to`; (3) fresh dry tyres at `wear_limit`; (4) if the two-compound rule is still unmet at `final_call`, stop now. Dry choice: medium → hard, otherwise → medium. |
| `RandomPolicy(seed, pit_chance=0.1)` | Stays out 90 % of the time, otherwise picks a random allowed stop |

## 5. Evaluation (`rl/evaluate.py`)

`compare(policies, seeds, **env_kwargs)` plays **every policy on the same seeds**, so each policy faces the same scenarios. `summarise(results, baseline)` reports, per policy:

- mean, sample standard deviation, minimum and maximum race time;
- mean stops;
- the number of penalised episodes;
- the **paired** difference to the baseline on each seed: mean ± standard deviation;
- how many seeds were better or worse than the baseline.

## 6. Learning experiment (`rl/experiment.py`)

- **Method:** the cross-entropy method over `RuleBased`'s 4 thresholds, within bounds `wear_limit` ∈ [0.3, 1], `neutral_from` ∈ [0, 0.8], `neutral_to` ∈ [0.2, 1], `final_call` ∈ [0.6, 0.98].
  - It starts at the hand-set values, with standard deviation = range ÷ 4.
  - Each iteration samples 8 candidates; the score is the mean total reward on **training seeds 0, 1 and 2**.
  - The 2 best become the new mean and spread. The best candidate ever seen is kept.
  - 3 iterations; the method's own random generator is seeded (0).
- **Evaluation:** all baselines plus the tuned policy on **seeds 100–119**, which were never used in training.
- **What "learning" means here:** tuning 4 numbers of a hand-designed rule by trial episodes. It is a minimal demonstration that the environment supports learning from repeated episodes. With 3 training episodes per candidate the tuning can easily overfit to those 3 scenarios, which is why it is evaluated on 20 others.

## 7. Results (one experiment: `python3 -m rl.experiment`, 53 laps)

These numbers are copied from [`rl/reports/experiment_report.md`](../../../rl/reports/experiment_report.md). Race time includes penalties; lower is better. "Paired" compares each policy with rule-based on the same seed.

**Held-out evaluation, seeds 100–119 (20 episodes):**

| Policy | Mean race time (s) | Std (s) | Mean stops | Penalised | Paired vs rule-based (s) | Better / worse than rule-based |
|---|---|---|---|---|---|---|
| stay out | 5233.3 | 130.3 | 0.00 | 20/20 | +40.7 ± 13.9 | 0 / 20 |
| fixed one-stop | 5196.8 | 129.1 | 1.00 | 0/20 | +4.2 ± 12.7 | 2 / 18 |
| **rule-based** (hand-set) | **5192.6** | 119.7 | 1.60 | 0/20 | — | — |
| random (10 % pit) | 5356.5 | 134.4 | 4.45 | 3/20 | +163.9 ± 108.9 | 0 / 20 |
| tuned rule-based (CEM) | 5192.8 | 118.3 | 1.55 | 0/20 | +0.2 ± 5.4 | 4 / 13 (3 ties) |

**Training, seeds 0–2.** The CEM run moved the thresholds from (wear 0.75, neutral 0.30–0.85, final call 0.85) to (0.915, 0.021–0.714, 0.885). The mean training reward improved from −55.6229 to −55.5726, about 4.7 s in total over the 3 races:

- −18.3 s in the one rain race (seed 2);
- +2.1 s in each of the two dry races.

**What this shows:**

1. **The interface works for comparing and tuning policies.** Paired, seeded evaluation separates policies clearly, even though race times vary by about ±120 s between scenarios.
   - The weather- and flag-aware rule-based policy beats a fixed one-stop on 18 of 20 races, by 4.2 s on average.
   - Staying out costs about 41 s, of which 30 s is the two-compound penalty.
   - Random stopping costs about 164 s.
2. **The tuning learned nothing that generalises.** On the held-out races it is +0.2 ± 5.4 s against the hand-set rule: worse on 13, better on 4. The paired spread is much larger than the mean.

   The cause is visible in the training data. **None of the 3 training scenarios had a VSC or Safety Car**, so the VSC/SC thresholds were never tested and drifted freely (neutral window 0.021–0.714). The other gains came from a single rain race. This is overfitting to an unrepresentative training set of 3 episodes, so no claim of a learned improvement is made.
3. **What would be needed** (not done here, V8 territory):
   - many more training episodes per candidate, with the scenarios stratified (dry, rain, VSC, SC);
   - more evaluation seeds;
   - a faster simulator.

   At about 2 s per episode, this experiment (24 candidates × 3 episodes + 100 evaluation episodes) already takes about 7 minutes.

## 8. How V6's findings limit what can be learned

| V6 finding | Consequence for learning |
|---|---|
| Model `pit_loss` is 22 s; Monza's measured loss is about 25.6 s | Stops look about 3.6 s cheaper than in reality, so learned policies may stop too often or too readily. `StrategyEnv(pit_loss=25.62)` uses the measured value. |
| Baseline laps are about 19 % slow; grip is not physical | Lap-time trade-offs (fresh tyres against stopping) are on the wrong scale. Learned thresholds are not transferable to real F1. |
| Tyre wear, compound grips, fuel effect, weather and race-control effects are unvalidated placeholders | The agent learns to exploit **this model's** tyre and weather behaviour, which may not exist in reality |
| Race-vs-qualifying pace is under-modelled (the calibrated race is 2–3 % too fast) | Degradation is too mild, which favours fewer stops and longer stints |
| Only Monza was checked | Nothing learned here says anything about other tracks |

Results are therefore statements about this simulator, not about Formula 1.

## 9. Limitations

1. **About 2 s per 53-lap episode:** tiny sample budgets, no deep RL.
2. **One controlled car,** pit decisions only; no fuel or refuelling actions.
3. **The reward is race time, not position.**
4. **Calls happen once per lap**, 300 m before the line. A flag shown after the call can only be acted on a lap later.
5. **The observation idealises tyre wear** (exact) and has no forecast.
6. **Opponents use fixed plans:** there is no multi-agent play (V8).
7. **Scenarios are simple:** at most one neutralisation, at most one shower, no retirements.
8. **The experiment is small:** 3 training seeds, 24 candidates, 20 evaluation seeds. Its result is not evidence of a good strategy beyond those seeds.
