# V2: Tyres, fuel and pit strategy (implementation)

## 1. Objective and scope

In V1 every car drove the same V0 flying lap, lap after lap, so a car's pace never changed during a race. In V2 two resources change lap by lap:

- **Tyres** wear out, and worn tyres have less grip.
- **Fuel** burns off, and less fuel means a lighter car.

A car can **pit** to fit new tyres and/or add fuel. That costs time. Each car follows a **strategy**: a fixed plan saying when to stop and what to fit.

In scope, as requested:

- the `TyreCompound` enum used in the simulation;
- tyre state separate from the car specification;
- a documented wear → grip relationship;
- fuel load and consumption, acting on mass through the existing physics;
- pit stops with a configurable pit loss;
- tyre changes and refuelling under explicit rules;
- a strategy representation;
- a deterministic strategy comparison;
- a pit-event log;
- strategy kept separate from physics and race progression.

Not in scope, and not implemented: tyre temperature, real degradation curves, a tyre "cliff" or failure, weather and wet tyres (V4), traffic and overtaking (V3), the mandatory two-compound rule and penalties (V5), calibration (V6), and strategy optimisation or ML (V7+).

**All tyre and fuel numbers in V2 are placeholders.** They were chosen by hand so the effects are visible and the strategies trade off against each other. They are not Pirelli, FIA or team data.

## 2. What was added or changed

| Item | Where | New / changed |
|---|---|---|
| `Compound`, `COMPOUNDS`, `WORN_GRIP_LOSS` | `tyres.py` | new: per-compound placeholder parameters |
| `Tyres` (`wear()`, `grip()`) | `tyres.py` | new: tyre state and the wear → grip model |
| `PitStop`, `Strategy` (`stop_after()`) | `strategy.py` | new: the strategy representation |
| `PIT_LOSS`, `FUEL_PER_LAP`, `FUEL_CAPACITY`, `REFUEL_RATE`, `FUEL_TOLERANCE` | `race.py` | new constants |
| `PitEvent` | `race.py` | new: one record per stop |
| `RaceCar` | `race.py` | changed: new `strategy`, `laps`, `fuel`, `tyres`, `pit_exit` fields |
| `LapProfile(car, track, tyre_grip, fuel)` | `race.py` | changed: builds the profile for a given grip and fuel load |
| `lap_profile()` | `race.py` | new: small cache around `LapProfile` |
| `Race` | `race.py` | changed: new settings, strategy validation, a new profile every lap, pit stops, `pit_events` |
| `tyre_grip` parameter | `physics.py`, `simulation.py` | changed: the friction coefficient is now an input, defaulting to V0's `TYRE_GRIP` |
| `main.py` | `main.py` | changed: two plans per team, strategy column, pit-stop log |

## 3. Who owns what

```
CarSpecification / Car   immutable car design (V0)                     cars.py, abstract_classes.py
Tyres                    one tyre set: compound + laps done            tyres.py
RaceCar                  one car's race state: distance, laps, fuel,   race.py
                         tyres, pit_exit, finish_time (+ refs to car and strategy)
Race                     race clock, rules and settings, applies       race.py
                         fuel/tyre/pit effects, pit-event log
Strategy / PitStop       decisions only: "after lap k, fit X, add Y kg" strategy.py
physics / simulate_lap   speed profile for one mass and one grip       physics.py, simulation.py
```

The responsibilities are separated as follows:

- **The strategy only decides.** `Strategy.stop_after(lap)` returns a `PitStop` or `None`. It never reads physics, never changes a car, and knows nothing about time.
- **The race applies the rules.** `Race` asks the strategy at each line crossing, then applies the stop. It also burns fuel and ages tyres.
- **The physics stays unaware of tyres and fuel.** It receives two numbers per lap, a mass and a grip coefficient, and computes a speed profile exactly as in V0.
- **Tyre state is a value.** `Tyres` is frozen, so wear is recorded by replacing the set with one that has one more lap. A `PitEvent` can therefore keep the "before" set safely.

Rejected alternative: putting fuel and tyre fields on `CarSpecification`. That would mix race state into the immutable design, and team-mates share one specification.

## 4. Tyre model

### 4.1 Compounds

| Compound | New-tyre grip μ₀ (dimensionless) | Wear per lap r | Laps to 100 % wear |
|---|---|---|---|
| SOFT | 1.83 | 0.05 | 20 |
| MEDIUM | 1.80 (= V0's `TYRE_GRIP`) | 0.03 | ≈ 33 |
| HARD | 1.775 | 0.02 | 50 |

`WORN_GRIP_LOSS = 0.06`: a fully worn tyre has 6 % less grip than new.

Where these numbers come from:

- MEDIUM's grip equals V0's single grip value, so a new medium with no fuel reproduces the V0 lap exactly.
- The others were picked so the softer compound is faster when new and wears faster. That is the qualitative pattern widely described for F1 compounds.
- The magnitudes are not measured. On the V0 physics at Monza, the McLaren's new soft is about 0.6 s/lap faster than a new medium, and a new hard about 0.5 s/lap slower.

`INTERMEDIATE` and `WET` exist in the enum but are not in `COMPOUNDS`. Wet tyres only make sense with weather (V4), so starting on them or fitting them raises `ValueError`.

### 4.2 Equations

Tyre state is `Tyres(compound, laps)`, where `laps` is how many laps this set has completed.

```
wear = min(1, laps × r)                        dimensionless, 0 = new, 1 = fully worn
μ    = μ₀ × (1 − WORN_GRIP_LOSS × wear)        dimensionless friction coefficient
```

So wear grows linearly, and grip falls linearly with wear. Once the set is fully worn, wear stays at 1. There is no further loss and no failure: grip has a floor at 94 % of new.

The performance metric is **μ**, the tyre friction coefficient. V0 already uses it in three places:

- corner speed limit: `v² = μ·m·g / (m/r − μ·½ρ·C_LA)`;
- grip available for accelerating or braking: `μ·(m·g + ½ρ·C_LA·v²)`, reduced by the cornering force;
- therefore the acceleration and braking limits.

Lower μ means lower corner speeds, later throttle and earlier braking. That makes the lap slower. It is the same effect V0 would show if you edited `TYRE_GRIP`.

### 4.3 How much time wear costs (model output)

On the McLaren at Monza, μ changes lap time by about −19 s per unit of μ. So +0.01 μ is about −0.19 s/lap.

One lap of wear costs:

| Compound | Grip lost per lap | Lap time added per lap |
|---|---|---|
| MEDIUM | 1.80 × 0.06 × 0.03 ≈ 0.0032 μ | ≈ +0.06 s |
| SOFT | ≈ 0.0055 μ | ≈ +0.10 s |
| HARD | ≈ 0.0021 μ | ≈ +0.04 s |

## 5. Fuel model

### 5.1 Parameters

| Constant | Value | Unit | Origin |
|---|---|---|---|
| `FUEL_PER_LAP` | 1.9 | kg/lap | Placeholder. 53 laps × 1.9 = 100.7 kg, close to a full race load. |
| `FUEL_CAPACITY` | 110 | kg | F1's maximum race fuel under the 2019–2025 rules, used here as the tank size |
| `REFUEL_RATE` | 10 | kg/s | Placeholder. Refuelling has been banned in F1 since 2010; this is a model option. |

### 5.2 Equations

Fuel is burned once per lap, at the line:

```
fuel(after lap k) = fuel(start) − k × FUEL_PER_LAP + fuel added at stops so far      kg
```

`CarSpecification.mass` (800 kg by default) is treated as the car plus driver with **no fuel**. For each lap, the physics sees:

```
m = spec.mass + fuel      kg
```

`LapProfile` passes this as `replace(spec, mass=spec.mass + fuel)`, a copy of the specification with a different mass. The original is never modified.

Mass enters the V0 equations in these places:

| V0 function | Mass dependence | Heavier car |
|---|---|---|
| `corner_speed` | `v² = μ m g / (m/r − μ·½ρ·C_LA)` | Lower corner speed, because downforce helps a smaller share of the weight |
| `acceleration` | `(drive − drag) / m` | Accelerates more slowly |
| `deceleration` | `(grip force + drag) / m` | Brakes less hard: weight adds grip, but downforce and drag do not grow with it |
| gradient term | `g × gradient / 100` | No mass effect |

Model output: at Monza, adding 10 kg costs the McLaren about 0.22 s/lap (≈ 0.021 s/kg). A full 100.7 kg load costs about 2.1 s/lap compared with V0's fuel-free lap. This sensitivity comes from the V0 physics; it has not been calibrated against real cars.

### 5.3 Fuel rules (checked before the race starts)

- Start fuel must be between 0 and `FUEL_CAPACITY`.
- At the start of every lap the car must hold at least `FUEL_PER_LAP`, otherwise the plan is rejected ("runs out of fuel on lap k").
- After a refuel, fuel must not exceed `FUEL_CAPACITY`.
- `FUEL_TOLERANCE = 10⁻⁹ kg` absorbs floating-point rounding. That way "exactly enough" fuel (53 × 1.9 kg) is accepted, and the car may finish with −10⁻¹³ kg.

Running out of fuel mid-race is not simulated. With a constant burn rate, a plan that would run dry can be detected up front, so it is rejected instead. Retirements belong to V5.

## 6. From per-lap state to a speed profile

### 6.1 Changes to V0 code: `tyre_grip`

1. **Limitation.** `corner_speed`, `longitudinal_grip`, `acceleration` and `deceleration` read the module constant `TYRE_GRIP`. `simulate_lap` could therefore only compute laps at μ = 1.8.
2. **Why V2 needs the change.** Tyre wear and compound change μ lap by lap.
3. **What it affects.** Each of those four functions, and `simulate_lap`, gets a `tyre_grip` parameter whose default is `TYRE_GRIP`. Every existing call behaves exactly as before. The V0 regression test (`test_monza_lap_times_unchanged_from_v0`) still passes with a 10⁻¹² tolerance.
4. **Alternatives considered.**
   - *Changing the global `TYRE_GRIP` before each lap:* hidden global mutable state.
   - *A `grip` field on `CarSpecification`:* mixes tyre state into the car design.

Mass needed no change to V0 code. `dataclasses.replace` gives the physics a specification with a different mass.

### 6.2 One profile per car per lap

`LapProfile(car, track, tyre_grip, fuel)` runs `simulate_lap` for that mass and grip. It then builds the same distance/time table as V1. With `tyre_grip=TYRE_GRIP` and `fuel=0` it is exactly V1's profile.

The race keeps **one current profile per car** in `Race._profiles`. At every line crossing, after fuel, tyres and any stop have been updated, the profile is rebuilt for the new state. Within a lap, mass and grip are constant.

Fuel burns continuously in reality; here it drops in 1.9 kg steps at the line. Wear behaves the same way.

**Cost.** One profile takes about 35 ms on Monza (5 900 points). A 53-lap, 8-car race needs up to 424 of them. `lap_profile()` is an `lru_cache(maxsize=16)` wrapper, keyed by `(car, track, grip, fuel)`. It reuses profiles when two cars are in exactly the same state, which happens for team-mates on the same plan and for V1-neutral races. `python3 main.py` takes about 11 s. The upgrade path, if that matters later, is interpolating between precomputed profiles.

### 6.3 Race progression with changing profiles

V1 converted a car's total distance into time using a single profile repeated forever. That no longer works when each lap has its own profile. `Race._advance(car, end)` now works one lap at a time:

```
loop until the car has finished or reached race time `end`:
    clock = max(clock, car.pit_exit)          # a car in the pits waits
    line  = next line crossing ahead (0 for a car still on the grid, else (laps+1)·L)
    lap_start = line − L
    start   = profile.time_at(distance − lap_start)   # s into this lap
    to_line = lap_time − start
    if the line is not reached before `end`:
        distance = lap_start + profile.distance_at(start + remaining time); stop
    clock += to_line;  distance = line         # exact crossing time
    if line > 0: complete the lap (fuel, tyres, finish or strategy, new profile)
```

Properties carried over from V1:

- Crossing times are exact, so results do not depend on `dt`. A test runs with `dt` = 3 s and 0.05 s, including a pit stop.
- One step can contain several crossings and a whole stop if `dt` is large.

`RaceCar.laps` now stores completed laps instead of deriving them from distance. Deriving `floor(distance / L)` exactly at a line can round down by one, and the lap loop must never double-count. `Race.laps_completed(car)` is kept for V1 callers and returns `car.laps`.

## 7. Pit stops

### 7.1 Rules

These are enforced by `Race._check` before the race starts. Each failure raises `ValueError` naming the car.

1. A stop happens **as the car completes lap k**, with 1 ≤ k ≤ race laps − 1. There are no stops before the start or as the car takes the flag. `k` must be an `int`.
2. At most one stop per lap.
3. A stop must change something: fit a set (`compound`) and/or add fuel (`fuel > 0`).
4. Only compounds in the race's `compounds` table may be fitted. By default these are the three dry compounds.
5. Fuel added must be ≥ 0, and the tank must not overflow (section 5.3).
6. A tyre change always fits a **new** set (`laps = 0`). `compound=None` keeps the current set, still ageing.

### 7.2 Timing

```
stop duration = pit_loss + fuel_added / REFUEL_RATE          s
```

`pit_loss` is a `Race` setting, default 22 s, a placeholder. It stands for everything a stop costs compared with driving past: the pit-lane speed limit, entry and exit, and the stationary time for a tyre change.

Refuelling time is added **on top**. The model does not run it in parallel with the tyre change, which is a deliberate simplification.

During the stop the car **stays at the line** (`distance = k·L`), and `pit_exit = crossing time + duration`. Steps before `pit_exit` do not move it. Other cars keep moving, so standings drop the stopped car naturally.

When it resumes, the car follows the new lap's profile from the line at that profile's flying speed. Pit-lane entry and exit are modelled only through `pit_loss`.

### 7.3 Pit-event log

Each stop appends a frozen `PitEvent` to `race.pit_events`. Its fields are `number`, `lap`, `time` (race time of the stop, s), `duration` (s), `tyres_before`, `tyres_after` (both `Tyres` values) and `fuel_added` (kg).

Events are stored in the order the race processed them: by step, then grid order within a step.

## 8. Strategy

```python
Strategy(compound, fuel, stops=(PitStop(lap, compound=None, fuel=0.0), ...), name="")
```

A strategy is a fixed plan: the starting compound, the starting fuel in kg, and stops at fixed laps. It is immutable and can be shared by several cars.

`RaceCar.strategy = None` means the default plan: no stops, on mediums, with exactly `laps × fuel_per_lap` of fuel.

The race consults the strategy at the line, through `stop_after(lap)`. A fixed plan is the simplest policy that "selects when to pit and which compound to use". A policy that reacts to race state (for example, pit when wear exceeds x) can be added later behind the same `stop_after` call. It is not needed for V2.

The FIA rule that a dry race must use two compounds is **not** enforced. It is a race-control rule (V5). For example, the "no stop (M)" plan breaks it.

## 9. Configuration options

| Where | Option | Default | Meaning |
|---|---|---|---|
| `Race(...)` | `pit_loss` | 22.0 s | Time a stop costs, before refuelling |
| `Race(...)` | `fuel_per_lap` | 1.9 kg | Fuel burned per lap (0 switches fuel effects off) |
| `Race(...)` | `compounds` | `COMPOUNDS` | Compound table: `{TyreCompound: Compound(grip, wear_per_lap)}` |
| `RaceCar(...)` | `strategy` | `None` | `Strategy`; `None` gives the default plan |
| `tyres.py` | `WORN_GRIP_LOSS` | 0.06 | Grip fraction lost at 100 % wear |
| `race.py` | `FUEL_CAPACITY`, `REFUEL_RATE` | 110 kg, 10 kg/s | Tank size, refuel speed |
| `main.py` | `strategies(laps)` | 2 plans | The plans each team runs |

**V1 behaviour** is this configuration:

```python
Race(track, laps, grid, fuel_per_lap=0.0, compounds={TyreCompound.MEDIUM: Compound(TYRE_GRIP, 0.0)})
```

With no strategy given, every car then runs on non-wearing mediums with no fuel. That is exactly V1. A new regression test reproduces V1's 53-lap Monza results to within 10⁻⁶ s; the actual difference is about 4 × 10⁻¹⁰ s.

## 10. Strategy comparison

These results come from the README example: the McLaren alone, 53 laps of Monza, default settings.

| Plan | Stops | Race time (s) |
|---|---|---|
| no stop, hard | 0 | 5124.340 |
| no stop, medium | 0 | 5116.691 |
| 1 stop: medium → hard after lap 26 | 1 | 5110.338 |
| 2 stops: soft → medium (17) → soft (35) | 2 | 5104.174 |
| 1 stop + refuel: medium, 26 laps of fuel → hard + 27 laps of fuel after lap 26 | 1 | 5087.915 |

What this shows:

- Here, stopping pays: the time new tyres regain is more than the 22 s pit loss.
- The refuelling plan beats the same medium → hard one-stop without refuelling by 22.4 s:
  - it carries about 25 kg less fuel on average, worth roughly 0.021 s/kg/lap × 25 kg × 53 laps ≈ 28 s;
  - it pays 51.3 kg ÷ 10 kg/s ≈ 5.1 s of extra stationary time.

  This is the trade-off behind refuelling strategies before 2010. The model only claims it is internally consistent.

The ranking depends entirely on the placeholder parameters. With no wear, the no-stop plan wins by exactly the pit loss (a test checks this). With heavy wear and a cheap stop, stopping wins (another test).

In `main.py`, each team runs one car on "no stop (M)" and one on "1 stop (M-H)" over 53 laps. On identical cars, the one-stop finishes ahead in every team: by 6.2 s for McLaren, 6.0 s for Red Bull, 5.7 s for Ferrari and 5.7 s for Mercedes.

## 11. Worked example: the McLaren's stop

Plan: start on mediums with 100.7 kg, stop after lap 26 for hards. Single car, grid slot 0, `dt = 0.5 s`.

| Moment | Fuel (kg) | Tyres | Wear | μ | Profile lap time (s) |
|---|---|---|---|---|---|
| Start, lap 1 | 100.7 | medium, 0 laps | 0.00 | 1.8000 | 96.1013 |
| Start of lap 26 | 53.2 | medium, 25 laps | 0.75 | 1.7190 | 96.7392 |
| After the stop, lap 27 | 51.3 | hard, 0 laps | 0.00 | 1.7750 | 95.5886 |
| Start of lap 28 | 49.4 | hard, 1 lap | 0.02 | 1.7729 | 95.5906 |

Notes on the table:

- Lap 1 is 2.1 s slower than V0's 93.998 s. That is the 100.7 kg of fuel.
- By lap 26, wear costs more than the fuel burned has saved.
- Fresh hards make the car 1.15 s/lap faster than worn mediums.
- On hards, wear and fuel burn nearly cancel (+0.002 s/lap).

The lap-26 crossing happens inside the step from 2506.5 s to 2507.0 s, at **2506.7709 s**. Then:

1. Fuel goes 53.2 → 51.3 kg. Tyres go to medium, 26 laps (wear 0.78).
2. The strategy returns `PitStop(26, HARD)`.
3. Duration = 22.0 + 0 / 10 = 22.0 s, so `pit_exit` = 2528.7709 s.
4. A `PitEvent(number=1, lap=26, time=2506.7709, duration=22.0, tyres_before=Tyres(MEDIUM, 26), tyres_after=Tyres(HARD, 0), fuel_added=0.0)` is logged.
5. The profile is rebuilt for hard tyres and 51.3 kg (μ = 1.775).
6. The car stays at 153 400 m (26 × 5 900 m) for the steps up to 2528.5 s.
7. In the step ending at 2529.0 s it leaves at 2528.7709 s and covers 13.12 m in the remaining 0.2291 s.

The car finishes at 5110.338 s with about 0 kg of fuel left, on hards with 27 laps of use.

## 12. Assumptions and limitations

1. **Placeholder parameters.** No compound, wear, fuel or pit value is calibrated (V6).
2. **Linear wear, linear grip loss, floor at full wear.** There is no tyre temperature, warm-up, graining, cliff or puncture.
3. **Updates once per lap.** Mass and grip are constant within a lap and step at the line.
4. **Fuel burn is constant per lap.** It does not depend on throttle, mass or traffic. The partial distance from the grid to the line burns no fuel.
5. **Pit box at the start/finish line.** There is no pit-lane geometry; `pit_loss` covers it. A car leaves at flying-lap speed.
6. **Refuelling is serial and optional.** It was banned in real F1 in 2010.
7. **Fixed plans only.** The two-compound rule is not enforced, there is no reactive or optimised strategy, and there is no undercut, because cars do not interact (V3).
8. **Wet compounds are rejected** until weather exists (V4).
9. **`lap_profile` cache keys on object identity.** Don't change a `Car` or `Track` while races are running.
10. **Runtime is about 35 ms per car-lap on Monza.** `python3 main.py` takes about 11 s.
11. **V1 limitations still apply:** rolling start, cars passing through each other, every car running the full distance.
