# V3: Traffic, overtaking, DRS and driver attributes (implementation)

## 1. Objective and scope

Up to V2, every car drove its own lap as if it were alone. Cars "passed" through one another as soon as one was quicker. In V3, cars **interact**:

- a car close behind another loses pace in corners (**dirty air**);
- a car within 1 s at the line gets **DRS** on the long straights of the next lap;
- a car cannot simply drive through the car ahead. It must meet an explicit **overtaking rule**, otherwise it is **held up** behind;
- each car has a **driver** whose `pace` and `racecraft` matter.

Passes and refused attempts are written to an event log, `race.overtakes`.

Not in scope, and not implemented: collision or contact models, side-by-side cornering geometry, aerodynamic wake simulation, sector-based DRS detection points, blue flags and lapped-car rules (V5), weather (V4), RL (V7).

**All thresholds and effects are model assumptions.** They are placeholders chosen so the behaviour is visible and plausible in order of magnitude. They are not FIA or team data.

## 2. What was added or changed

| Item | Where | New / changed |
|---|---|---|
| `Driver(name, pace, racecraft)`, `PACE_SPREAD` | `drivers.py` | new |
| `TrafficRules` (thresholds), `is_straight`, `is_drs_zone`, `time_factor`, `drs_enabled`, `required_advantage`, `can_attack` | `traffic.py` | new: race rules as plain functions |
| `OvertakeEvent` | `race.py` | new: event record |
| `RaceCar.driver`, `.drs`, `.attack`, `.held_by` | `race.py` | new fields |
| `LapProfile.speed`, `.speed_at()` | `race.py` | new: speed at any distance |
| `Race(traffic=TrafficRules())`, `race.overtakes` | `race.py` | new setting and log; `traffic=None` restores V2 |
| `Race.step`, `_drive`, `_advance(factor, limit)` | `race.py` | changed: race-order processing, traffic effects, holding a car behind another |
| `Race.car_ahead`, `Race.interval` | `race.py` | new public helpers for nearby cars |
| `_next_line`, `_on_track`, `_segment`, `_free_distance`, `_speed` | `race.py` | new internal helpers |
| `main.py` | `main.py` | `DT` 0.5 → 0.1 s; overtake log printed |

## 3. Who owns what

```
Car / CarSpecification   the machine: power, drag, downforce, mass          (V0, unchanged)
Driver                   the person: pace, racecraft                         drivers.py
TrafficRules + functions the rules: thresholds, effects, pass conditions     traffic.py
Strategy                 pit decisions                                       (V2, unchanged)
RaceCar                  one car's race state, including traffic state       race.py
Race                     orchestration: who is near whom, order of           race.py
                         processing, applying rules, logging events
```

- The rule functions in `traffic.py` are pure. They take numbers, segments and drivers and return a factor or a yes/no. They never touch race state, so they can be tested without a race.
- `Race` decides **when** to ask the rules and **what to do** with the answer.
- A `Driver` is immutable and validated. Team-mates in identical cars can still differ through their drivers.

## 4. State

### 4.1 New per-car state (`RaceCar`)

| Field | Type | Meaning |
|---|---|---|
| `driver` | `Driver` | Input, default `Driver()`: pace 1.0, racecraft 0.5 |
| `drs` | `bool` | DRS may be used on the current lap. Set at each line crossing. |
| `attack` | `OvertakeEvent \| None` | A pass in progress, holding the numbers that allowed it |
| `held_by` | `int \| None` | Number of the car this one is stuck behind |

Inherited state keeps its meaning:

- **track position** is `distance`, in metres since the start line;
- the position within the current lap is `distance % track.length`;
- the track segment at that point comes from `Race._segment(car)`.

### 4.2 New race state

- `race.traffic`: the `TrafficRules` in force, or `None`.
- `race.overtakes`: the event log.
- `_segment_starts`: the end position of each segment except the last, used to find the segment at any distance with `bisect`.

## 5. Nearby competitors

### 5.1 `Race.car_ahead(car)`

The **car ahead** is the nearest car with a greater `distance` that is **on track**. On track means:

- not finished; and
- not in the pits (`pit_exit ≤ race.time`).

The leader has no car ahead.

Because `distance` counts total metres, "ahead" means ahead **in the race**. A car a lap down that happens to be just in front on the road is not "ahead" of the leader. Lapped traffic therefore does not interact (see §12).

### 5.2 `Race.interval(car, ahead)`

```
interval = T_follower(ahead.distance) − T_follower(car.distance)        s
```

`T` is the follower's current lap profile (`time_at`, with the distance taken relative to the start of the follower's lap). In words: the time the follower would need, at its own current pace, to reach the spot where the car ahead is now. This is close to what F1 timing shows as the interval, without needing the cars' history.

Example: 8 m behind on the Stadium test track, where the car does 34 m/s, gives an interval of 0.235 s.

## 6. How effects change a car's pace: the time factor

Each car on its V2 lap profile can be slowed or sped up by a **time factor** `f`. The factor stretches profile time:

```
race time to cover a stretch = profile time for that stretch × f
speed                        = profile speed / f
```

`Race._advance(car, end, factor, limit)` applies this. With `f = 1` and no limit, it is exactly V2's code path. For a car on track, `f` is decided once per step, at the car's position at the start of the step:

```
f = driver factor × dirty-air factor × DRS factor
driver factor   = 1 + PACE_SPREAD × (1 − pace)                          PACE_SPREAD = 0.01
dirty air       = 1 + dirty_air_loss   if in a corner and interval < dirty_air_interval
DRS             = 1 − drs_gain         if car.drs and on a DRS-zone straight
```

## 7. Driver attributes

| Attribute | Range | Effect | Default |
|---|---|---|---|
| `pace` | 0–1 | Lap-time factor `1 + 0.01 × (1 − pace)`. Pace 0 is 1 % slower, about 0.95 s/lap at Monza. Applied with or without traffic. | 1.0 (no loss, so V2 is unchanged) |
| `racecraft` | 0–1 | Shifts the speed advantage needed to pass. Used both when attacking and when defending. | 0.5 |
| `name` | text | Label only | `""` |

Validation in `Driver.__post_init__`: `pace` and `racecraft` must be real numbers in [0, 1]. `bool`, strings, `None` and NaN all raise `ValueError`.

**Why only these two attributes?**

- `pace` lets two drivers differ in identical cars, which creates traffic between team-mates.
- `racecraft` makes the outcome of a fight depend on the people as well as the machines.
- *Consistency* would need lap-to-lap randomness. The brief asks for determinism unless a seeded random component is designed, and none is needed here.
- *Tyre management* would change V2's wear model. It is deferred until there is a reason to calibrate wear (V6).

## 8. Dirty air

**Rule.** A car whose interval to the car ahead is **under 1.0 s** (`dirty_air_interval`) is slower **in corners** by 2 % (`dirty_air_loss`). On straights there is no dirty-air effect. The slipstream gain is folded into DRS rather than modelled separately.

**Why corners only.** The disturbed wake mostly costs downforce, and downforce matters most in corners. The V0 model's corner speeds depend on it.

At Monza, a car that spends a whole lap in dirty air loses about 0.6–0.8 s. That is model output from 2 % of the corner time.

## 9. DRS

**Detection.** When a car crosses the line, at the end of its move in that step, it gets DRS for the lap it is starting if all of these hold:

1. That lap number is at least `drs_from_lap = 3`. In other words, no DRS on laps 1 and 2.
2. There is a car ahead on track.
3. The interval to that car is **strictly less than** `drs_interval = 1.0 s`.
4. The car itself is not in the pits after this crossing.

Otherwise `drs = False`. That is how DRS **deactivates**: it is re-decided at every crossing.

**Zones.** DRS works on straights at least `drs_min_straight = 500 m` long. At Monza that is the 1 210 m main straight and the 980 m straight before the Parabolica. Real Monza also has two DRS zones, though not with exactly these boundaries.

**Effect.** In a zone, the time factor is multiplied by `1 − 0.035`, which means about 3.6 % more speed (≈ +3.5 m/s at 100 m/s). It is worth roughly 0.8 s over a Monza lap.

## 10. Overtaking

### 10.1 When an attempt happens

Each step, for a car with a car ahead and no pass in progress:

1. Compute where it would end the step with nobody in its way (`_free_distance`).
2. If that is **closer than `min_gap = 5 m`** to where the car ahead **now** is (the car ahead has already moved this step), then this step is an **attempt**.

### 10.2 How it is decided

```
advantage = v_attacker(x) / f_attacker − v_defender(x) / f_defender          m/s
required  = overtake_margin − racecraft_effect × (racecraft_attacker − racecraft_defender)
          = 2.0 − 1.0 × (Δ racecraft)      → between 1.0 and 3.0 m/s

attack allowed  ⇔  attacker's segment is a straight  and  advantage ≥ required
```

- `x` is the **attacker's** position. Both speeds are read from each car's own lap profile at that same spot. The question is "who is quicker through this bit of track", not "who is quicker right now at two different places".
- The speed difference comes from everything that affects the profile or factor:
  - the car design (V0);
  - tyre grip and fuel mass (V2);
  - driver pace;
  - dirty air;
  - DRS.

**A higher nominal speed is not enough.** The attacker needs a margin of at least 1 m/s, and 2 m/s between equal drivers. It also has to be on a straight; braking zones at the end of a straight count, because the segment there is still the straight.

### 10.3 Outcomes

| Decision | What happens | Event logged |
|---|---|---|
| **Allowed** | `car.attack` is set. From now on the car moves freely, as in V2. | — |
| …attacker gets ahead (`distance > defender.distance`) | Positions swap in `standings()` | `"passed"` |
| …attacker falls more than `min_gap` behind | The attack ends | `"aborted"` |
| **Refused** | The car may not pass `ahead.distance − min_gap` this step (`limit`). It stops there and waits out the step. | `"held up"`, only when it becomes held behind that car, not on every step |

**Position update.** Race position is still `standings()`, which sorts by distance (V1). An overtake is therefore just the attacker's distance becoming larger than the defender's. Nothing else needs updating.

`OvertakeEvent` fields:

- `time`: end of the step;
- `lap`: the attacker's current lap;
- `attacker`, `defender`: car numbers;
- `outcome`;
- `advantage` and `required`, from the deciding step;
- `drs`: whether the attacker had DRS.

## 11. Event ordering inside one step

1. The race takes `standings()` at the start of the step. That is race order, leader first.
2. Cars are processed **in that order**. Each car therefore sees the car ahead **after** it has moved this step.
3. For each car on track (`_drive`):
   1. find the car ahead and its interval;
   2. look up the segment;
   3. compute the time factor;
   4. if the attack's defender is no longer the car ahead (it pitted or finished), drop the attack;
   5. make the pass decision (§10);
   6. move with `_advance(factor, limit)`, which handles line crossings, fuel, tyres and pit stops exactly as in V2;
   7. resolve the attack (passed or aborted);
   8. if a line was crossed, run DRS detection.
4. Cars in the pits, or finished, are moved with their driver factor only. They are not obstacles, and they are not blocked.
5. `race.time` advances.

Without traffic (`traffic=None`) the loop runs in grid order, exactly as in V2.

## 12. Interaction with V1 and V2

- **Pit stops.** A car in the pits is off track: it neither blocks nor is blocked. Cars driving past it are **not** logged as overtakes, though they gain the position in `standings()`. When it rejoins it is a normal car on track again.
- **Tyres and fuel** change the lap profile (V2). They therefore change the speeds used in `advantage`. Fresh grippy tyres can make a pass possible (tested).
- **Finished cars** leave the track.
- **`traffic=None`** gives V2 behaviour exactly. Regression tests check V2's recorded results to 10⁻⁶ s (the actual difference is about 3 × 10⁻¹² s), and V1's.
- **Step size now matters.** In V1 and V2, results did not depend on `dt`, because each car's motion was exact. Interactions are decided once per step, so with traffic they do. In the 53-lap, 8-car Monza race:

  | `dt` | Passes | Winner's time |
  |---|---|---|
  | 0.5 s | 31 | 5110.8 s |
  | 0.25 s | 33 | 5112.7 s |
  | 0.1 s | 17 | 5124.7 s |
  | 0.05 s | 21 | 5123.7 s |

  At 0.1 and 0.05 s the top two pairs agree within about 1 s, while close midfield fights still move by up to about 7 s. Fights decided right at a threshold (for example 1.91 vs 2.00 m/s) can flip with `dt`.

  `main.py` uses `DT = 0.1 s`. It takes about 19 s, of which about 10 s is V2's per-lap physics.

## 13. Worked example

Two cars, 8 laps of Monza, `pit_loss = 4 s`, default rules and drivers:

- #1 Mercedes, mediums, no stop;
- #2 McLaren, mediums, stops after lap 1 for softs.

| Time | What happens |
|---|---|
| 1.9 s | #2 is 5 m behind #1 on the main straight. Its free move would close within 5 m, so this is an attempt. Advantage +1.49 m/s against the 2.0 m/s required: **held up**. |
| 92.0 s | It is close again in the Parabolica (a corner). Advantage +3.41 m/s, but not on a straight: **held up**. |
| 95.7 s | #2 pits (4 s) and fits softs. It rejoins about 4.0 s behind. |
| 193.5 s | Interval 2.10 s. #2 is gaining 1–2 s per lap: faster car, fresh softs. |
| 281.0 s | In the Parabolica, the interval used for #2's step drops just under 1.0 s (it was 1.094 s at 280.0 s). **Dirty air** is on: factor ×1.02 in corners. |
| 287.4 s | #2 completes lap 3 with an interval of 0.432 s. Lap 4 ≥ 3, so **DRS on**. |
| 297.9 s | Main straight (a DRS zone, factor 0.965). Advantage +1.907 m/s, below 2.0: **held up**, kept 5 m behind. |
| 299.4 s | About 1 090 m down the straight, #1 is already braking for Turn 1 at this spot: 95.99 m/s against #2's 101.46 m/s. Advantage +5.466 m/s ≥ 2.0, so the attack is allowed. |
| 299.8 s | #2 is at 18 834.99 m and #1 at 18 834.90 m: **passed**. `standings()` becomes [#2, #1]. |
| 299.9 s | Now #1 is the follower, with advantage −6.67 m/s: **held up** behind #2. |

CODE_FLOW.md §4 goes through the deciding steps line by line.

## 14. Main race (`python3 main.py`)

This is the same 8-car, two-plans-per-team race as V2, now with traffic:

- 17 passes; cars were held up 372 times;
- most passes come in the second half with DRS, as one-stoppers on fresh hards come through;
- the order and times differ from V2. The same strategy can now lose time behind a slower car.

For example, the Ferrari and Mercedes cars finish within 1.1 s of each other, as a DRS train.

## 15. Assumptions and limitations

1. **One dimension.** There is no lateral position. "Side by side" just means two cars closer than `min_gap` during an allowed attack.
2. **Lapped cars do not interact**, because "car ahead" means ahead in the race. There are no blue flags (V5).
3. **No defensive moves.** The defender's only influence is its racecraft.
4. **A refused car waits at `ahead − min_gap`** for the rest of the step. Its speed inside the step is not smooth.
5. **At most one pass per car per step.** Only the immediate car ahead is checked.
6. **Decisions use the state at the start of the step** (segment, factor), and events are stamped with the end of the step. Their time resolution is `dt`.
7. **Results depend on `dt`** (§12) and are sensitive near thresholds. They are deterministic for identical inputs and `dt`.
8. **Identical cars with DRS can swap places repeatedly** ("DRS ping-pong"). This is an emergent consequence of the rules.
9. **The "held up" count has hysteresis.** A car stuck behind another for a whole stint is logged again each time it catches up after falling back in a corner.
10. **`car_ahead` checks every car each step**, so the cost grows with the square of the number of cars. That is fine for 8 cars.
11. **All rule values are placeholders** (V6 calibration). There are no collisions, contact, damage or incidents (V5).
