# P2-V1: Driver skills and profiles

Phase 2 milestone 1 of 6. This version gives the driver a full profile of abilities. Only two new skills, `attack` and `defence`, have an effect in the simulator so far. The other three are stored and validated but have **no effect yet**, and this document says what they will do later.

Line numbers below are from the P2-V1 commit and may shift in later versions; symbol names are the stable reference.

## 1. Scope and objective

**Objective:** extend `drivers.Driver` with five independently configurable skills (`attack`, `defence`, `tyre_management`, `consistency`, `wet_weather`) and give each one a precise definition.

**In scope:**
- the new fields, their defaults and validation;
- a decision on what `racecraft` means from now on;
- wiring `attack` and `defence` into the existing overtaking rule, because that can be done without new mechanisms (section 5.3);
- tests and documentation.

**Out of scope (later milestones):**
- any driver *decision*: when to attack, when to save tyres, how hard to push (P2-V2 adds driver observations, actions and rule-based policies);
- any new physical control of the car: throttle, braking, corner approach (P2-V3);
- an RL driver (P2-V4), driver-versus-driver evaluation (P2-V5), and connecting the driver to the strategist (P2-V6).

## 2. What existed before (inherited, unchanged in meaning)

From V3 (see [V3 IMPLEMENTATION.md](../../versions/v3/IMPLEMENTATION.md)), `drivers.Driver` was a frozen dataclass with three fields:

| Field | Meaning in V3–V9 | Where it is used |
|---|---|---|
| `name` | label only | printing |
| `pace` (0–1, default 1.0) | how close the driver drives to the car's limit | `Driver.time_factor()`: lap time × (1 + 0.01 × (1 − pace)) |
| `racecraft` (0–1, default 0.5) | wheel-to-wheel skill, used both when attacking and when defending | `traffic.required_advantage()` |

`__post_init__` rejected booleans, non-numbers and values outside 0–1 for `pace` and `racecraft`.

The overtaking rule (V3) works like this. When a car would close to within `TrafficRules.min_gap` (5 m) of the car ahead, `Race._drive` compares the two cars' speeds at the follower's position. A pass can start only on a straight, and only if the follower is faster by at least the *required advantage*:

```
required (m/s) = overtake_margin − racecraft_effect × (attacker.racecraft − defender.racecraft)
```

With the defaults (`overtake_margin` = 2.0 m/s, `racecraft_effect` = 1.0 m/s per unit) this ranges from 1.0 m/s (best attacker against worst defender) to 3.0 m/s (the reverse). Otherwise the follower is held 5 m behind.

The strategist (`rl/env.py`, V7/V9) never sets a driver: every car in it uses `Driver()`.

## 3. What is new

| Field | Default | Has an effect in P2-V1? |
|---|---|---|
| `attack` | `None`, which becomes `racecraft` | **Yes**: lowers the speed advantage this driver needs to pass |
| `defence` | `None`, which becomes `racecraft` | **Yes**: raises the speed advantage a rival needs to pass this driver |
| `tyre_management` | 0.5 | No (profile only) |
| `consistency` | 0.5 | No (profile only) |
| `wet_weather` | 0.5 | No (profile only) |

Other changes:
- `racecraft` is now documented as the **general wheel-to-wheel skill**: the value that `attack` and `defence` take when they are not given.
- Every skill (old and new) goes through the same validation loop.
- `traffic.required_advantage` now reads the attacker's `attack` and the defender's `defence` instead of both drivers' `racecraft`.

## 4. The profile, attribute by attribute

Every skill is a number from 0 (weakest in this model) to 1 (best in this model). The scale is a **model input**: 0.7 does not mean "70 % as good as a real driver", and no value here is a measurement of a real person. Tests and examples use fictional drivers.

### 4.1 `pace` (inherited)
- **Definition:** how close to the car's performance limit the driver drives on a clear track.
- **Range / default:** 0–1, default 1.0 (exactly at the limit the physics computes).
- **Effect:** `Driver.time_factor()` = 1 + `PACE_SPREAD` × (1 − pace), with `PACE_SPREAD` = 0.01 (placeholder). A pace-0 driver takes 1 % longer everywhere (about 0.95 s per lap at Monza).
- **Not modelled:** where on the lap the time is lost. It is a uniform stretch of the lap profile, not slower braking or cornering.

### 4.2 `racecraft` (inherited, role clarified)
- **Definition:** general wheel-to-wheel skill. It is now the default for both `attack` and `defence`.
- **Range / default:** 0–1, default 0.5.
- **Effect:** none of its own once both `attack` and `defence` are given. It still decides every race where they are not given, which includes every race written before P2-V1.
- See section 5.2 for why it was kept.

### 4.3 `attack` (new, integrated)
- **Definition:** how small a speed advantage this driver needs before starting a pass. It stands for skills the model does not represent separately: placing the car, choosing the moment, braking later into the next corner.
- **Range / default:** 0–1. `None` (the default) means "use `racecraft`".
- **Effect:** in `traffic.required_advantage`, each unit of the attacker's `attack` lowers the required advantage by `racecraft_effect` m/s (1.0 by default).
- **What attack does NOT do:** it does not make the car faster, it does not change dirty air or DRS, and it does not decide *whether* the driver tries. In this simulator every follower tries whenever the rule allows. "Decides to attack more often" is a decision and belongs to a P2-V2 driver policy.

### 4.4 `defence` (new, integrated)
- **Definition:** how large a speed advantage a rival needs before starting a pass on this driver. It stands for positioning and covering the inside line.
- **Range / default:** 0–1. `None` (the default) means "use `racecraft`".
- **Effect:** in `traffic.required_advantage`, each unit of the defender's `defence` raises the required advantage by `racecraft_effect` m/s.
- **What defence does NOT do:** it does not slow the attacker, block a pass already in progress, or cost the defender time. Defending has no cost in this model (section 9).

### 4.5 `tyre_management` (new, profile only)
- **Definition:** how little pace the driver gives up to reduce tyre wear by a given amount.
- **Range / default:** 0–1, default 0.5.
- **Effect in P2-V1:** **none**. No code outside `drivers.py` and the tests reads it. `test_profile_only_skills_do_not_change_a_race_yet` checks that a race is bit-identical with the value at 0 and at 1.
- **Planned mechanism (not implemented, may change):** a driver policy (P2-V2) chooses a tyre-saving level `s` from 0 (no saving) to 1 (maximum saving). Saving reduces wear per lap and costs time. The skill sets the *exchange rate*: for the same wear saved, a better manager loses less time. A proposal:

  ```
  wear per lap   = compound wear_per_lap × (1 − s × MAX_SAVING)
  time factor   *= 1 + s × MAX_SAVING_COST × (1 − tyre_management × SKILL_DISCOUNT)
  ```

  This is a trade-off, not a free bonus: a driver who never chooses to save gains nothing from the skill.
- **Why not now:** there is no decision yet (that is P2-V2), and `tyres.Tyres` counts wear in whole laps (`Tyres.wear()` = `laps` × `wear_per_lap`). A per-lap wear rate that can change needs a fractional wear field on `Tyres`, which changes a public class and belongs with the milestone that uses it.

### 4.6 `consistency` (new, profile only)
- **Definition:** how little the driver's performance varies from lap to lap without a reason (no traffic, weather or tyre change behind it).
- **Range / default:** 0–1, default 0.5.
- **Effect in P2-V1:** **none** (same test as 4.5).
- **Planned mechanism (not implemented, may change):** every lap gets a small random time factor drawn from a seeded random generator, with spread σ = `MAX_SPREAD` × (1 − consistency). A consistency-1 driver repeats the same lap; a consistency-0 driver varies most. The average lap time should not change, only the spread.
- **Why not now:** the race is fully deterministic today, and some regression tests depend on that. Adding randomness needs an explicit, seeded random source owned by the race, and a decision about how it interacts with the strategist environment's seeds. That design belongs with on-track control (P2-V3).

### 4.7 `wet_weather` (new, profile only)
- **Definition:** how much of the remaining grip the driver can use when the track is wet (low grip).
- **Range / default:** 0–1, default 0.5.
- **Effect in P2-V1:** **none** (same test as 4.5).
- **Planned mechanism (not implemented, may change):** today the V4 weather model lowers tyre grip with wetness (`Tyres.grip(compounds, wetness)`), and every driver drives exactly at that lower limit. The skill would decide how close to the reduced limit the driver can drive, with the gap growing with wetness and shrinking with skill. On a dry track (wetness 0) the effect must be exactly zero.
- **Why not now:** the simplest version would be another fixed lap-time multiplier in the wet, and the master prompt asks not to substitute multipliers for behaviour. The better model ties the skill to how much margin a driver chooses to keep on low grip, which needs the driver controls of P2-V3.

## 5. Design reasoning

### 5.1 Profile versus policy
A `Driver` describes what the driver *can* do. It contains no decisions and no state that changes during a race (it is frozen). Decisions will live in separate policy objects from P2-V2 on, which read the profile. This keeps two questions apart: "is this driver good at saving tyres?" (profile) and "should this driver save tyres now?" (policy).

### 5.2 What to do with `racecraft`
The prompt asks not to make `racecraft` silently redundant. Options considered:

| Option | Problem |
|---|---|
| Remove `racecraft`, use only `attack` and `defence` | Breaks every existing `Driver(racecraft=...)` call, test and README example |
| Keep `racecraft` in the formula and add `attack`/`defence` on top | Two terms for the same thing: double counting, and a meaningless "racecraft" bonus |
| Store `attack`/`defence` with no effect, keep the formula on `racecraft` | Safe, but leaves two fields that look meaningful and do nothing, although the formula already separates attacker skill from defender skill |
| **Chosen:** `racecraft` is the default for `attack` and `defence`; the formula uses `attack` and `defence` | Old calls behave exactly as before. New calls can set the two separately. When both are given, `racecraft` has no effect, and this is documented |

So `racecraft` is the **general wheel-to-wheel attribute**: a one-number shortcut that sets both roles. It is not deprecated.

### 5.3 Why attack and defence could be integrated now
The V3 formula already contains one term for the attacker and one for the defender:
`attacker.racecraft − defender.racecraft`. Splitting it into `attacker.attack − defender.defence` is a relabelling of an existing mechanism, not a new bonus. It adds no new constant and no new behaviour. With the defaults, or with only `racecraft` set, every number is identical to V3. This passes the prompt's test: "can be implemented coherently and tested without introducing a premature driver-control system".

### 5.4 Why `None` means "use racecraft"
A default of 0.5 for `attack` would break `Driver(racecraft=0.9)`: its attack would become 0.5 and old races would change. `None` lets the dataclass know whether the caller gave a value. `__post_init__` replaces `None` with `racecraft` before validation, so after construction `attack` and `defence` are always numbers (they are never `None` on a finished `Driver`).

## 6. How the new code interacts with the rest

- **`race.RaceCar.driver`** (`race.py:34`) stores the profile. Nothing in `Race` changes it.
- **`race.Race._drive`** (`race.py:336`) calls `required_advantage(rules, car.driver, ahead.driver)` and `can_attack(...)`. Both now read `attack`/`defence`. `Race` itself is unchanged.
- **`traffic.time_factor`** and **`race_control.RaceControl.pace_factor`** still use only `Driver.time_factor()`, so only `pace` affects speed.
- **The strategist** (`rl/env.py`) is unchanged. All its cars use `Driver()`, whose resolved values give the same numbers as V9, so its results are unchanged.
- **The V8 research results** (`research/results/scenario_coverage.json`) store a digest of all non-test `.py` files. Changing `drivers.py` and `traffic.py` changes the digest, so the experiment was re-run (see the CHANGELOG for the result comparison).

## 7. Equations and units

Required speed advantage (m/s), `traffic.required_advantage`:

```
required = overtake_margin − racecraft_effect × (attacker.attack − defender.defence)
```

| Symbol | Unit | Default | Source |
|---|---|---|---|
| `overtake_margin` | m/s | 2.0 | `TrafficRules`, V3 placeholder |
| `racecraft_effect` | m/s per unit of skill | 1.0 | `TrafficRules`, V3 placeholder (name kept for compatibility) |
| `attacker.attack`, `defender.defence` | dimensionless, 0–1 | `racecraft` (0.5) | `Driver` |

Range with the defaults: 1.0 m/s (attack 1, defence 0) to 3.0 m/s (attack 0, defence 1). Two default drivers: 2.0 m/s.

A pass starts only if `can_attack` holds: the attacker is on a straight (`radius == inf`) **and** its speed advantage ≥ `required`. The advantage is measured, not assumed: `Race._speed` gives each car's lap-profile speed at the attacker's position, divided by that car's time factor for this step (pace, dirty air, DRS, flags).

Lap-time factor (unchanged), `Driver.time_factor`: `1 + PACE_SPREAD × (1 − pace)`, dimensionless, `PACE_SPREAD` = 0.01.

## 8. Configuration and validation

`Driver(name="", pace=1.0, racecraft=0.5, attack=None, defence=None, tyre_management=0.5, consistency=0.5, wet_weather=0.5)`

- The first three positions are unchanged, so `Driver("A", 0.5, 1)` still means name, pace, racecraft. Pass the new skills by keyword.
- `__post_init__` (`drivers.py:20`):
  1. replaces `attack=None` / `defence=None` with `racecraft`;
  2. checks every field after `name`, in declaration order. Each must be an `int` or `float`, not a `bool`, with 0 ≤ value ≤ 1.
- That one comparison also rejects NaN (every comparison with NaN is false), +∞ and −∞. Strings, lists and `None` (outside `attack`/`defence`) fail the type check.
- The error is a `ValueError` that starts with the skill's name, e.g. `defence must be a number from 0 to 1, got 1.2`.
- An invalid `racecraft` is reported as `racecraft`, not as `attack`, because `racecraft` is checked first.
- `Driver` is frozen: changing a field after construction raises `dataclasses.FrozenInstanceError`. Two drivers never share state.
- `name` is not validated (as in V3).

## 9. Assumptions, limitations and known weaknesses

- **Linear and symmetric.** One unit of attack is worth exactly as much as one unit of defence (`racecraft_effect` m/s). This is a modelling choice with no data behind it.
- **Defence is free and passive.** A defender loses no time by defending and cannot react. A real defender gives up time on the inside line.
- **No randomness.** The same speeds and skills always give the same outcome. A real pass attempt can fail.
- **Attack does not affect the attempt once started.** A pass in progress succeeds or is aborted only on speed (`Race._drive`).
- **`racecraft_effect` is now a slightly misleading name.** It scales attack − defence. It is kept so existing `TrafficRules(...)` calls keep working.
- **Three skills do nothing yet.** `tyre_management`, `consistency` and `wet_weather` must not be described as affecting results until a later milestone gives them a mechanism. A test guards this.
- **Skill values are not ratings.** They are configurable inputs. They must not be read as measurements of real drivers.
- **Name clash to be aware of:** `RaceCar.attack` (an `OvertakeEvent` or `None`: a pass in progress) and `Driver.attack` (a float skill) are different things. Code reads the skill as `car.driver.attack`.

## 10. Worked example (Monza, 6 laps)

Three fictional drivers race on `MonzaV0`, as in the README's V3 traffic example. A Mercedes ("Defender", racecraft 0.9) leads two identical McLarens: "Rookie" (racecraft 0.1) and "Veteran" (racecraft 0.9). Then the same race is run with one change: the Rookie gets `defence=0.9` and keeps `attack=0.1` (from its racecraft).

```
V3 racecraft only: #3 Veteran 567.052 s, #2 Rookie 568.365 s, #1 Defender 574.202 s
  lap 5  400.5 s  #3 on #2: aborted advantage +1.31 m/s, needed 1.20, DRS
  lap 6  486.6 s  #3 on #2: passed  advantage +3.55 m/s, needed 1.20, DRS
Rookie defence 0.9: #2 Rookie 567.518 s, #3 Veteran 568.149 s, #1 Defender 574.202 s
  (no pass attempts by #3 on #2; held up 15 times instead of 14)
```

1. **The first run is exactly the V3 result** (same times to the millisecond as the README). The profiles resolve to attack = defence = racecraft, so `required_advantage` returns the V3 numbers.
2. **Veteran attacking Rookie, first run:** required = 2.0 − 1.0 × (0.9 − 0.1) = **1.2 m/s**. On lap 5 the Veteran has +1.31 m/s, so an attempt starts (later aborted); on lap 6 it passes with +3.55 m/s.
3. **Second run:** required = 2.0 − 1.0 × (0.9 − **0.9**) = **2.0 m/s**. On lap 5 the Veteran's +1.31 m/s is not enough: logged as `held up`. The logged lap-6 check shows +1.25 m/s. No later check met both conditions (on a straight, at least 2.0 m/s faster), so no attempt is ever logged, and the Rookie wins. (A `held up` event is logged only when a car first gets stuck behind another, not at every step.)
4. **The Rookie's own attack is unchanged** (0.1). Its pass on the Defender still needs 2.0 − (0.1 − 0.9) = 2.8 m/s, as in V3. Only the defence changed, and only the races where the Rookie defends changed.

The run takes about 3 s per race. `test_defence_alone_decides_whether_a_pass_happens` checks the same effect on a small test track.

## 11. Why this is a suitable foundation for P2-V2

- P2-V2 will define driver observations and actions. A policy can read the profile (`driver.attack`, `driver.tyre_management`, ...) as fixed parameters without the profile containing any decision.
- `attack` and `defence` already enter the one place where a wheel-to-wheel decision happens (`Race._drive`). A P2-V2 "attack now or wait" decision can sit next to it.
- The three profile-only skills have written definitions and planned mechanisms. Each later milestone can be checked against them, and `test_profile_only_skills_do_not_change_a_race_yet` must be updated (not deleted) when a skill gains an effect.
