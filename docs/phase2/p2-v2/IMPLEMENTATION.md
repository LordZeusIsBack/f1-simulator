# P2-V2: Driver decision interfaces and rule-based baseline policies

Phase 2 milestone 2 of 6. This version defines how a driver **observes** the race and **chooses** an on-track action, and adds three rule-based driving styles. The actions are **proposals only**: in P2-V2 no action changes how a car moves or whether a pass happens. The race decides that exactly as in P2-V1. P2-V3 will connect the actions to the car.

Line numbers below are from the P2-V2 commit and may shift in later versions; symbol names are the stable reference. Everything new is in one module, `driving.py`.

## 1. Scope and objective

**Objective:** an explicit decision interface for the driver, separate from the strategist's, plus interpretable baseline policies that use the P2-V1 skill profile.

**In scope:**
- a driver observation built from the race, with validation;
- four actions and a rule saying when each is available;
- a policy interface and a checker for what policies return;
- three baseline policies (conservative, balanced, aggressive);
- a harness that runs a race, asks the policies before every step and logs their decisions.

**Out of scope:**
- any physical effect of an action (P2-V3);
- RL, training or rewards for the driver (P2-V4);
- throttle or brake commands (they need P2-V3's control model first).

## 2. What existed before

- **P2-V1:** `drivers.Driver` has `pace`, `racecraft`, `attack`, `defence`, `tyre_management`, `consistency` and `wet_weather`. Only `pace`, `attack` and `defence` affect a race (see [P2-V1 IMPLEMENTATION.md](../p2-v1/IMPLEMENTATION.md)).
- **The race makes every on-track choice itself.** In `Race._drive`, a follower that would close to within 5 m of the car ahead attempts a pass whenever `traffic.can_attack` allows it (a straight, and a speed advantage ≥ `required_advantage`). Otherwise it is held behind. Nobody chooses to attack, defend or save tyres.
- **The strategist** (`rl/env.py`, `rl/policies.py`) chooses pit stops once per lap: `policy(observation, mask) -> int`. It is unchanged.

## 3. What is new (all in `driving.py`)

| Symbol | Kind | Purpose |
|---|---|---|
| `DriverAction` (line 23) | `Enum` | `MAINTAIN_PACE`, `ATTACK`, `DEFEND`, `CONSERVE_TYRES` |
| `DriverObservation` (line 31) | frozen dataclass | What a driver may use, in physical units, validated on construction |
| `Decision` (line 72) | `NamedTuple` | What a policy returns: `action`, `reason`, `features` |
| `DriverPolicy` | type alias | `Callable[[DriverObservation, Driver], Decision]` |
| `DecisionRecord` (line 81) | `NamedTuple` | One log entry: `time`, `car`, `lap`, `action`, `reason`, `features` |
| `available_actions` (line 91) | function | Which actions make sense in this observation |
| `decide` (line 101) | function | Calls a policy and rejects invalid or unavailable actions |
| `observe` (line 132) | function | Builds the `DriverObservation` of one car from a `Race` |
| `run` (line 157) | function | Runs a race to the end, asks the policies before every step, logs changes of action |
| `RuleBasedDriver` (line 180) | frozen dataclass, callable | One rule-based policy with four thresholds |
| `CONSERVATIVE`, `BALANCED`, `AGGRESSIVE`, `BASELINES` (lines 216-219) | instances | The three baseline styles |
| `ATTACK_SKILL_SPAN`, `DEFENCE_SKILL_SPAN`, `TYRE_SKILL_SPAN` (lines 18-20) | constants | How much the skills shift the thresholds (placeholders) |

No existing file's code changed. `race.py`, `traffic.py`, `drivers.py` and `rl/` are untouched.

## 4. The observation schema

`DriverObservation` holds 12 fields. They were chosen from the prompt's list, and each one is either used by the baselines or needed to tell whether an action is available.

| Field | Type, unit | Range | Source in the race | Why it is included |
|---|---|---|---|---|
| `laps_remaining` | int | ≥ 0 | `race.laps − car.laps − 1` | Saving tyres on the last lap is pointless |
| `speed` | float, m/s | ≥ 0 | own lap-profile speed here ÷ own time factor | Pace awareness; the basis of `closing_speed` |
| `on_straight` | bool | | `traffic.is_straight(race._segment(car))` | Segment context: the race lets a pass start only on a straight |
| `gap_ahead` | float, s, or `None` | ≥ 0 | `race.interval(car, ahead)` | Is there a car to attack, and how close? |
| `closing_speed` | float, m/s, or `None` | any finite | own speed − ahead car's speed, **both at this car's position** | Is this car faster than the car ahead right here? |
| `gap_behind` | float, s, or `None` | ≥ 0 | `race.interval(behind, car)` | Is there a car to defend against, and how close? |
| `compound` | `TyreCompound` | | `car.tyres.compound` | Tyre state (logged; not used by the baselines yet) |
| `tyre_wear` | float | 0–1 | `car.tyres.wear(race.compounds)` | When to conserve tyres |
| `wetness` | float | 0–1 | `race.weather.wetness`, else 0 | Weather state (not used by the baselines yet; see §9) |
| `flag` | `race_control.Flag` | | `race.race_control.flag`, else `GREEN` | Race-control state |
| `overtaking_allowed` | bool | | `race._overtaking_allowed(car)` | Flags can forbid passing here (yellow zone, VSC, SC) |
| `drs` | bool | | `car.drs and race._drs_allowed()` | Whether DRS is usable on this lap |

**Missing data is `None`, never a made-up number.** The leader has `gap_ahead = closing_speed = None`, the last car has `gap_behind = None`, and a car racing alone has all three `None`. A race without weather reports `wetness = 0.0`, and a race without race control reports `flag = GREEN` and `overtaking_allowed = True`. This matches how those races behave.

**Deliberately excluded:**
- the rivals' skills (a driver cannot see a rival's `defence`);
- the strategist's hidden scenario values (pit loss, fuel burn, wear rate);
- positions and other cars' tyres;
- the `Race` and `RaceCar` objects themselves.

A policy cannot reach race state through the observation: it is a frozen dataclass of plain values.

**`closing_speed` uses exactly the race's own numbers.** `_factor(race, car)` (line 115) repeats the time-factor calculation in `Race._drive`: pace, dirty air in corners when following within 1 s, DRS on long straights, then race control's `pace_factor`. Then `_speed` divides the lap-profile speed by it. In a check on the Monza example, the first 8 `OvertakeEvent`s the race logged each had an `advantage` equal to the observation's `closing_speed` from just before that step, to 3 decimals.

**Validation** (`DriverObservation.__post_init__`, line 46) collects every problem and raises one `ValueError` that names the fields:
- numbers must be finite ints or floats, and not `bool`;
- gaps and speed must be ≥ 0, and wear and wetness must be 0–1;
- `closing_speed` must be a number exactly when `gap_ahead` is (both `None` or both given);
- `compound`, `flag` and the three bools must have their declared types.

## 5. The actions

| Action | Intended meaning | Available when | Physical effect in P2-V2 |
|---|---|---|---|
| `MAINTAIN_PACE` | Drive as the race model does | always | none (it is what the car already does) |
| `ATTACK` | Try to pass the car ahead | a car ahead **and** `overtaking_allowed` | **none** |
| `DEFEND` | Protect the position from the car behind | a car behind **and** `overtaking_allowed` | **none** |
| `CONSERVE_TYRES` | Give up some pace to save tyre wear | always | **none** |

**Not connected yet, and what P2-V3 has to add:**
- **`ATTACK`:** today every follower attempts a pass whenever the race's rule allows. P2-V3 can make an attempt require `ATTACK`, and may let attacking cost tyre wear or risk.
- **`DEFEND`:** today defending is passive (the defender's `defence` skill raises the required advantage). P2-V3 can make that effect depend on `DEFEND` and give defending a cost in lap time.
- **`CONSERVE_TYRES`:** needs fractional tyre wear and a pace-for-wear trade whose exchange rate is set by `tyre_management` (P2-V1 IMPLEMENTATION.md §4.5).

No `PUSH`, throttle or brake action exists: the simulator could not carry it out, and the prompt rules out commands without a physical model.

`test_run_logs_changes_of_action_with_reasons_and_does_not_change_the_race` checks the "proposals only" claim. A race run through `driving.run` with all three policies has exactly the same finish times and overtakes as `race.run`.

## 6. The policy interface

```python
DriverPolicy = Callable[[DriverObservation, Driver], Decision]
```

- **Input:** the observation and the driver's skill profile. The profile is passed separately because it describes the driver's capabilities and never changes during a race; the observation describes the situation and changes every step. A policy object holds only its own thresholds, so one policy can drive any number of drivers.
- **Output:** a `Decision(action, reason, features)`:
  - `action` is a `DriverAction`;
  - `reason` is a short machine-readable code;
  - `features` is a small dict of the numbers the rule compared, including the skill-adjusted threshold.
- **Checking:** `decide(policy, observation, driver)` raises `ValueError` if the result is not a `Decision` with a `DriverAction`, or if the action is not in `available_actions(observation)`.

**How this differs from the strategist's interface** (`rl/policies.py`):

| | Strategist | Driver (P2-V2) |
|---|---|---|
| Signature | `policy(observation, mask) -> int` | `policy(observation, driver) -> Decision` |
| When | once per lap, 300 m before the line | before every race step (0.1 s by default) |
| Observation | `rl.env.Observation`, 19 floats in [0, 1] | `driving.DriverObservation`, 12 fields in physical units |
| Action | integer: stay out / pit for a compound | `DriverAction` enum |
| Unavailable actions | `mask` tuple | `available_actions(observation)` |

Both use the same idea of a callable that sees only an observation, never the simulator.

## 7. How each baseline decides

`RuleBasedDriver.__call__` (line 195) checks three rules in a fixed order and returns the first that fires.

1. **Attack** if `ATTACK` is available, `gap_ahead ≤ attack_gap`, and `closing_speed > needed`, where
   `needed = max(0, attack_margin − ATTACK_SKILL_SPAN × (driver.attack − 0.5))` (m/s).
   Reason `close_and_faster`; features `gap_ahead`, `closing_speed`, `needed`.
2. **Defend** if `DEFEND` is available and `gap_behind ≤ window`, where
   `window = max(0, defend_gap + DEFENCE_SKILL_SPAN × (driver.defence − 0.5))` (s).
   Reason `car_behind_close`; features `gap_behind`, `window`.
3. **Conserve tyres** if the policy conserves at all (`conserve_wear` is not `None`), `laps_remaining > 0`, and `tyre_wear ≥ start`, where
   `start = conserve_wear − TYRE_SKILL_SPAN × (driver.tyre_management − 0.5)`.
   Reason `tyres_worn`; features `tyre_wear`, `conserve_from`.
4. Otherwise **maintain pace**: reason `no_trigger`, no features.

Fighting comes before saving tyres, and attacking before defending. A car with a car close behind and a slower car close ahead attacks.

The three baselines use the same rules with different thresholds (values for a 0.5 skill):

| | `attack_gap` (s) | `attack_margin` (m/s) | `defend_gap` (s) | `conserve_wear` |
|---|---|---|---|---|
| `CONSERVATIVE` | 0.5 | 2.0 | 0.3 | 0.3 |
| `BALANCED` | 1.0 | 1.0 | 0.6 | 0.6 |
| `AGGRESSIVE` | 1.5 | 0.3 | 1.0 | `None` (never) |

What the labels mean in behaviour (each line is a test in `test_driving.py`):
- **Conservative** attacks only when very close (≤ 0.5 s) **and** much faster (> 2 m/s). It defends only at ≤ 0.3 s and starts saving tyres at 30 % wear.
- **Balanced** attacks within 1 s when more than 1 m/s faster, defends within 0.6 s, and saves tyres from 60 % wear.
- **Aggressive** attacks within 1.5 s at any closing speed above 0.3 m/s. It defends within 1 s (the DRS detection interval, so it defends whenever the car behind could get DRS) and never chooses to save tyres.

All the threshold values are **placeholders** chosen to order the three styles. They are not fitted to data.

## 8. How the skill profile changes decisions

Each skill shifts one threshold linearly. A skill of 0.5 leaves the preset value unchanged.

| Skill | Threshold it shifts | Per unit of skill | Direction and reason |
|---|---|---|---|
| `attack` | `needed` closing speed | −1.0 m/s (`ATTACK_SKILL_SPAN`) | A better attacker attacks with a smaller speed advantage, because the race's rule lets it pass with less (P2-V1 `required_advantage`) |
| `defence` | defending `window` | +0.5 s (`DEFENCE_SKILL_SPAN`) | A better defender defends earlier, because defending works better for it |
| `tyre_management` | wear at which to start conserving | −0.2 (`TYRE_SKILL_SPAN`) | A better manager starts saving earlier, because saving will cost it less pace (planned P2-V3 trade-off) |

`consistency` and `wet_weather` are not used by the baselines (§9).

**A high skill does not guarantee success, or even an attack:**
- `needed` is floored at 0 and the comparison is strict (`closing_speed > needed`), so even `attack = 1.0` never chooses `ATTACK` against a car it is not faster than;
- choosing `ATTACK` does not start a pass. The race's own rule still decides, and that rule also uses the *defender's* `defence`, which the driver cannot observe. In the worked example (§11) the Rookie's policy needs 1.4 m/s, but the race requires 2.8 m/s.

## 9. Assumptions, limitations and known weaknesses

- **Proposals only.** No action changes the race. Any analysis of "which baseline is better" must wait for P2-V3.
- **Instantaneous rules flicker.** Closing speed changes from corner to corner, so a policy can switch between `ATTACK` and `MAINTAIN_PACE` several times a lap. The log records every switch. No hysteresis was added (not needed until actions have effects).
- **Every step is a decision.** `run` calls each policy before every race step, but logs only changes. With `dt` = 0.1 s that is ten decisions per second per car. They are cheap pure functions.
- **The observation is perfect.** Gaps and speeds are exact model values, with no noise or delay.
- **The observer reads `Race`'s private helpers** (`_segment`, `_profiles`, `_in_zone`, `_drs_allowed`, `_overtaking_allowed`, `_on_track`). This avoids widening `Race`'s public API, at the price of coupling `driving.py` to `race.py` internals. It is marked with a `ponytail:` comment.
- **`_factor` copies `Race._drive`'s calculation.** If `_drive` changes, `_factor` must change with it. The equality is checked only by the manual comparison in §4, not by a test.
- **`wetness`, `compound`, `on_straight`, `drs`, `flag` and `speed` are observed but not used by the baselines.** They are there for logging, for availability (`flag` through `overtaking_allowed`), and for later policies. `wet_weather` and `consistency` therefore have no effect on decisions yet.
- **The rule order is fixed.** Attack, then defend, then conserve. A policy that prefers defending would need its own class.
- **Policies run only through `driving.run` or direct calls.** `Race.run` and the strategist do not call them.

## 10. Configuration and validation

- `RuleBasedDriver(name, attack_gap, attack_margin, defend_gap, conserve_wear)`: the first three must be ≥ 0, and `conserve_wear` must be `None` or 0–1. Anything else raises `ValueError`.
- `run(race, policies, dt=0.1)`: `policies` maps car numbers to policies. A number not in the race raises `ValueError`. Cars without a policy race as normal and are not logged. The race is run to the finish.
- `observe(race, car)` raises `ValueError` for a car that is not on track (finished, retired or in the pits).

## 11. Worked example (Monza, 6 laps)

The README's three fictional drivers on `MonzaV0`: Defender (#1, Mercedes, racecraft 0.9) uses `CONSERVATIVE`, Rookie (#2, McLaren, racecraft 0.1) uses `BALANCED`, and Veteran (#3, McLaren, racecraft 0.9) uses `AGGRESSIVE`.

**At 12.6 s the Rookie closes on the Defender** on the main straight (segment 0, a 1,210 m `Straight`). `observe(race, car_2)` returns:

```
laps_remaining=5, speed=97.90, on_straight=True, gap_ahead=0.149, closing_speed=4.508,
gap_behind=0.131, compound=MEDIUM, tyre_wear=0.0, wetness=0.0, flag=GREEN, overtaking_allowed=True, drs=False
```

`closing_speed` = 97.90 − 93.40 m/s. 93.40 m/s is the Mercedes's lap-profile speed at the Rookie's position; both time factors are 1.0 here (pace 1, no dirty air on a straight, no DRS on lap 1).

`BALANCED(obs, rookie)`:
1. `ATTACK` is available, and gap 0.149 s ≤ `attack_gap` 1.0 s.
2. `needed` = max(0, 1.0 − 1.0 × (0.1 − 0.5)) = **1.4 m/s**: a weak attacker needs more.
3. 4.508 > 1.4, so the result is `Decision(ATTACK, "close_and_faster", {"gap_ahead": 0.149, "closing_speed": 4.508, "needed": 1.4})`.

The previous logged action was `DEFEND` (from 2.0 s, the Veteran 0.137 s behind), so `run` appends a `DecisionRecord(12.6, 2, 1, ATTACK, ...)`.

**What the race does:** nothing different. At 13.6 s the Rookie reaches the braking zone, its closing speed drops below 1.4 m/s, and the policy switches to `DEFEND` (Veteran 0.131 s behind, window 0.6 + 0.5 × (0.1 − 0.5) = 0.4 s). At 13.7 s the race itself logs `held up`: advantage 1.372 m/s against a required 2.8 m/s. The 2.8 comes from 2.0 − (Rookie's attack 0.1 − Defender's defence 0.9), and the driver could not have known the Defender's defence. Final times are the same as without policies: `#3 567.052 s, #2 568.365 s, #1 574.202 s`.

Over the race, the Rookie's log has 15 `ATTACK`, 19 `DEFEND` and 5 `MAINTAIN_PACE` records; the aggressive Veteran's has 28 `ATTACK`, 3 `DEFEND` and 27 `MAINTAIN_PACE`; the conservative Defender's has 1 `ATTACK`, 3 `DEFEND` and 4 `MAINTAIN_PACE`.

## 12. Why this is a suitable foundation for P2-V3

- P2-V3 has one place to plug in effects: the `DriverAction` a car chose. For example, `Race._drive` could require `ATTACK` before an attempt starts, apply a defensive-line cost on `DEFEND`, and apply a wear/pace trade on `CONSERVE_TYRES`.
- `run` already produces the decision for every car before every step, which is the information P2-V3 needs.
- The observation is in physical units, validated, and limited to what a driver may know. P2-V4 can turn it into an RL observation by scaling, as `rl.env` did for the strategist.
- The baselines are transparent, so they can serve as P2-V4's comparison policies.
