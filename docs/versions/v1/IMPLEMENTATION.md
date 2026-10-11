# V1: Multi-car race simulation (implementation)

## 1. Objective and scope

V0 could answer one question: "how long does one flying lap take for this car on this track?"
V1 answers a new question: "if several cars start a race of N laps together, who is where at any moment, and in what order do they finish?"

In scope for V1:

- Car configuration kept separate from per-race car state.
- Teams fielding two cars that share one car configuration but move independently.
- A race state: participating cars, elapsed race time, distance covered and completion.
- A simple, deterministic starting grid (no qualifying).
- Cars progressing around the existing track, lap after lap.
- Positions calculated from race progress.
- Output: position, car number, team, laps completed, gaps.
- An explicit finish condition: a configured lap count.
- The V0 flying-lap function kept, unchanged in behaviour.
- Reproducible results for the same inputs.

Deliberately **not** in V1 (see section 8): tyres, fuel, pit stops, overtaking rules, car-to-car interaction, weather, flags, safety car and qualifying.

## 2. What was added

| Item | Where | Purpose |
|---|---|---|
| `track_points(track)` | `simulation.py` | Splits a track into ~1 m pieces. It was previously a few lines inside `simulate_lap`; now `simulate_lap` and the race both use it. |
| `RaceCar` | `race.py` | One car in one race: number, team, shared `Car` configuration, plus its own `distance` and `finish_time`. |
| `LapProfile` | `race.py` | Turns the V0 speed profile into a lookup table between distance and time, repeated every lap. |
| `Race` | `race.py` | Holds the race state (track, lap count, cars in grid order, race clock). It places cars on the grid, advances them (`step`), ranks them (`standings`) and decides when the race is over (`finished`). |
| `GRID_SPACING` | `race.py` | 8 m between grid slots. |
| Race output | `main.py` | After the V0 lap printout, runs a two-cars-per-team race and prints standings after lap 1 and at the finish. |
| Tests | `test_race.py`, `test_simulation.py` | See CHANGELOG.md. |

## 3. Inherited V0 model (unchanged, summarised so V1 makes sense)

V1 does not change any physics. It only reuses V0's output. For reference, these are the units V0 already uses. They were never written down before.

| Quantity | Unit / meaning | Status |
|---|---|---|
| `CarSpecification.power` | W (740 000 W = 740 kW) | Placeholder value |
| `CarSpecification.drag`, `.downforce` | m² — drag/lift coefficient multiplied by reference area (C·A), used as `area` in `aero()` | Placeholder value |
| `CarSpecification.mass` | kg (default 800) | Placeholder value |
| `TrackSegment.length` | m | Approximate for Monza |
| `TrackSegment.radius` | m; `inf` for a straight | Approximate for Monza |
| `TrackSegment.gradient` | percent (1.1 = 1.1 % uphill); the code uses `G * gradient / 100`, a small-angle approximation | Approximate for Monza |
| `AIR_DENSITY` | 1.225 kg/m³ (standard sea-level air) | Physical constant, fixed |
| `TYRE_GRIP` | dimensionless friction coefficient 1.8 | Tuning parameter |

V0's `simulate_lap(car, track)` returns `(lap_time, speed)`:

- `lap_time` is in seconds.
- `speed[i]` is the speed in m/s at track point `i`.

The profile is a **flying lap**: the car crosses the start line already at speed, and the speed at the end of the lap equals the speed at its start. Section 4.2 relies on this.

## 4. Architecture

```
abstract_classes.py   Car, CarSpecification, Track ...   (V0, unchanged)
cars.py               CARS: team name -> Car            (V0, unchanged)
tracks.py             Monza                             (V0, unchanged)
physics.py            forces and speed limits           (V0, unchanged)
simulation.py         track_points, simulate_lap        (V0, track_points extracted)
race.py               RaceCar, LapProfile, Race         (new in V1)
main.py               V0 lap printout + V1 race         (extended)
```

### 4.1 Configuration versus state

V1 separates three kinds of data:

| Kind | Class | Who owns it | Changes during a race? |
|---|---|---|---|
| Car design (power, drag, downforce, mass) | `Car` / `CarSpecification` (V0) | Shared by both cars of a team | No |
| One car's progress in this race | `RaceCar` | One per car on the grid | Yes: `distance`, `finish_time` |
| The race as a whole | `Race` | One per race | Yes: `time`; reads/writes its `RaceCar`s |

Team-mates hold **the same `Car` object** (`first.car is second.car` is `True`), but each has its own `RaceCar`. Moving one never moves the other. A test checks this.

**Why not put the state on `Car`?**
The `Car` objects in `cars.py` are module-level and shared. Storing race progress on them would create global mutable state. Two team-mates sharing one `Car` would also share one distance. Instead, `RaceCar` points to a `Car`.

**Why no `Team` class?**
In V1 a team is only a name plus a car design, and `CARS` already maps one to the other. A `Team` class would hold exactly those two things and add nothing. `RaceCar.team` is a plain string. Add a `Team` class when teams carry state of their own.

### 4.2 Reusing the V0 speed profile: `LapProfile`

The V0 profile gives a speed at each ~1 m point. A race needs two questions answered for any car:

1. "The car is at distance D. How long after leaving the start line did it get there?"
2. "It is now time τ. How far has the car got?"

`LapProfile` answers both by building two parallel lists, one entry per track point plus a closing entry:

```
distance[0] = 0            time[0] = 0
distance[j+1] = distance[j] + ds_j
time[j+1]     = time[j]     + 2 · ds_j / (v_j + v_{j+1})
```

Here `ds_j` (m) is the length of piece `j` from `track_points`, and `v_j` (m/s) is the V0 speed at point `j`. The point after the last one wraps back to point 0.

`2·ds/(v_j + v_{j+1})` is the time to cover `ds` at the average of the two end speeds. This is exact if acceleration is constant over the piece, a reasonable assumption for a 1 m piece. It is the same formula `simulate_lap` uses for `lap_time`. Therefore `time[-1]` equals the V0 lap time, and `distance[-1]` equals the track length. A test checks both.

Because the profile is a flying lap, every lap is identical. For any total distance `D` (any lap, even negative):

```
laps, rest = divmod(D, L)                    L = track length (m)
T(D) = laps · T_lap + interpolate(rest)      T_lap = lap time (s)
```

The inverse is built the same way:

```
laps, rest = divmod(τ, T_lap)
D(τ) = laps · L + interpolate(rest)
```

`interpolate` finds the two table entries around `rest` with `bisect` (standard library) and draws a straight line between them.

Python's `divmod` rounds towards minus infinity. So for D = −8 m on a 5 900 m track it gives `laps = −1`, `rest = 5 892 m`. That is "8 m before the line, on the lap before lap 1", exactly what a car on the grid needs.

### 4.3 Time progression: fixed steps, exact positions

`Race.step(dt)` advances the race clock by `dt` seconds. For each car that has not finished:

```
τ0 = T(distance)           where the car is on its own time axis
distance = D(τ0 + dt)      where it is dt seconds later
```

This is a **fixed time step**, but no integration error builds up. Position is not computed as `distance += speed · dt`. It is read back from the car's own time/distance table, so `dt` only decides how often we look at the race.

I ran the full 53-lap, 8-car Monza race twice, once with `dt = 3 s` and once with `dt = 0.05 s`. The finish times differed by at most 3 × 10⁻⁹ s. The automated test makes the same comparison on a small test track, with a 10⁻⁶ s tolerance.

Alternatives considered:

- **Euler integration (`distance += v · dt`).** Error accumulates with every step, especially in braking zones. Race lap times would then depend on `dt` and no longer match V0's lap time.
- **An event-driven engine.** It would schedule line crossings as events. That is unnecessary: in V1 cars do not interact, so nothing happens between steps that a step could miss.
- **A closed-form solution with no stepping.** Each car's finish time could be computed directly, since cars are independent in V1. We rejected this because the prompt asks for race progress and a race state. A step also gives later versions one place to change a car's progress during the race.

`dt` defaults to 0.5 s in `Race.run` and `main.py`. A full 53-lap Monza race with 8 cars runs in well under a second.

### 4.4 Starting grid

`Race.__init__` takes the grid as a list. The **list order is the grid order**. The car in slot `k` (0-based) starts at:

```
distance = −k · GRID_SPACING = −8k m
```

That means `k · 8` metres behind the start line. `GRID_SPACING = 8.0 m` is a model assumption, roughly the stagger of a real F1 grid. The sideways offset of the two grid columns is ignored. Distance is measured along the track only.

`main.py` builds the grid from `CARS` in its listed order, two cars per team, numbered 1–8:

| Slot | Car | Start distance |
|---|---|---|
| 0 | #1 Red Bull | 0 m |
| 1 | #2 Red Bull | −8 m |
| 2 | #3 Ferrari | −16 m |
| 3 | #4 Ferrari | −24 m |
| 4 | #5 McLaren | −32 m |
| 5 | #6 McLaren | −40 m |
| 6 | #7 Mercedes | −48 m |
| 7 | #8 Mercedes | −56 m |

This order is a deterministic input, not a result of qualifying, and the car numbers are not real F1 numbers. Positions *during* the race never use this order, except to break exact ties (section 4.5).

**Rolling start.** Because each car follows its flying-lap profile from the first metre, it is already moving at the speed its profile has `8k` metres before the line. There is no standing start from 0 m/s. Section 8 explains the effect.

### 4.5 Positions

`Race.standings()` sorts the cars with this key:

- Finished car: `(0, finish_time)`. All finished cars come first, the earliest finisher first.
- Running car: `(1, −distance)`. Running cars come next, the furthest along first.

A finished car is always ahead of a running one: it has completed every lap, and a running car has not. Python's `sorted` is stable, so cars with exactly equal keys keep grid order. That keeps the result deterministic even when two cars are at the same distance.

Dictionary order is never used for positions.

### 4.6 Laps and race completion

- `Race.race_distance = laps · track.length` (m).
- `laps_completed(car)` is `floor(distance / L)`, never below 0. A grid car at −8 m has completed 0 laps, not −1. A finished car reports exactly `laps`, which avoids floating-point rounding at the boundary.
- A car **finishes** in the step where its new distance reaches `race_distance`. Its `finish_time` is not the end of the step. It is the exact moment it crossed the line:

  ```
  finish_time = race.time + T(race_distance) − τ0
  ```

  `race.time` is the clock at the start of the step. `T(race_distance) − τ0` is how far into the step the line was reached. The car's `distance` is then set to exactly `race_distance` and it stops moving.
- The **race is over** (`race.finished`) when every car has finished.

This finish rule is simpler than real F1. In F1 the chequered flag ends everyone's race at their next line crossing after the winner, so lapped cars run fewer laps. In V1 every car runs the full distance. The chequered flag is a race-control event and belongs to V5.

### 4.7 Validation of inputs

| Input | Rejected when | Error |
|---|---|---|
| `laps` | not an `int`, or `< 1` (0, −1, 2.5, "3") | `ValueError` |
| `grid` | empty | `ValueError` |
| car numbers | two cars share a number (numbers identify cars and key their profiles) | `ValueError` |
| `dt` in `step` | `<= 0` | `ValueError` |
| `main.py` laps argument | not an integer | `ValueError` from `int()` |

## 5. Interaction with V0

- `simulate_lap` keeps its signature, return value and numerical results. Before V1 it built its track points inline. Now it calls `track_points`, which contains the same lines. A new regression test compares all four Monza lap times with the values recorded at the V0 commit `76f1562`, to 12 significant digits.
- `LapProfile` calls `simulate_lap` once per car and `track_points` once per car. It reads but never modifies anything from V0.
- `main.py` still prints the V0 flying-lap table first, unchanged. The race output follows it.

Why `track_points` was extracted (changing an existing function):

1. **Limitation:** `simulate_lap` built the list of `(ds, radius, gradient)` points internally and returned only `(lap_time, speed)`. A speed list alone cannot be mapped to distances, because each piece is `segment.length / n` m, not exactly 1 m (a 50π m corner is cut into 157 pieces of 1.0005 m).
2. **Why V1 needs it:** `LapProfile` needs each piece's length to build its distance/time table.
3. **What it affects:** only `simulate_lap`'s internals. Behaviour is identical, and the regression test shows it.
4. **Alternatives considered:**
   - Changing `simulate_lap`'s return value would break its callers.
   - Copying the loop into `race.py` would leave two copies to drift apart.
   - Assuming exactly 1 m per piece would be wrong, as shown above.

## 6. Worked example: two cars, two laps

`Race(Monza(), 2, [#1 Red Bull, #2 McLaren])` with `dt = 0.5 s`.

**Setup.** Monza is L = 5 900 m and the race distance is 11 800 m.

| | Red Bull #1 | McLaren #2 |
|---|---|---|
| Grid slot / start distance | 0 / 0 m | 1 / −8 m |
| V0 lap time `T_lap` | 94.5546 s | 93.9983 s |
| `time_at(start)` | 0 s | −0.1372 s |

The McLaren's −0.1372 s means its profile needs 0.137 s to cover the last 8 m before the line. It is 8 m behind, travelling at about 58 m/s.

**First steps.**

| Race time | Car | distance before | τ0 = T(d) | τ0 + 0.5 | distance after |
|---|---|---|---|---|---|
| 0.0 s | #1 | 0.000 m | 0.000000 s | 0.500000 s | 29.664 m |
| 0.0 s | #2 | −8.000 m | −0.137210 s | 0.362790 s | 21.950 m |
| 0.5 s | #1 | 29.664 m | 0.500000 s | 1.000000 s | 62.164 m |
| 0.5 s | #2 | 21.950 m | 0.362790 s | 0.862790 s | 54.561 m |
| 1.0 s | #1 | 62.164 m | 1.000000 s | 1.500000 s | 97.055 m |
| 1.0 s | #2 | 54.561 m | 0.862790 s | 1.362790 s | 89.514 m |

Take the McLaren's first step. `divmod(−8, 5900)` gives `(−1, 5892)`, so

```
T(−8) = −1 · 93.9983 + interpolate(5892) = −0.1372 s
```

Adding 0.5 s gives 0.3628 s. Then `divmod(0.3628, 93.9983)` gives `(0, 0.3628)`, and interpolating in the time column gives 21.950 m.

After 1.5 s the standings are #1 (97.1 m), #2 (89.5 m): Red Bull leads.

**Position change.** The McLaren is quicker over a lap, so it closes the 8 m gap. At race time 53.0 s it is at 3 164.70 m and the Red Bull at 3 164.64 m, so `standings()` now puts #2 first. There is no interaction in V1, so it passes "through" the Red Bull.

**Finish of #2.** At race time 188.0 s the McLaren is at 11 792.19 m (τ0 = 187.8628 s). One more step would take it to 11 822.16 m, past the 11 800 m race distance. So:

```
T(11 800)   = 2 · 93.99834 = 187.99669 s
finish_time = 188.0 + (187.99669 − 187.86279) = 188.13389 s
```

Cross-check: two laps at 93.99834 s, plus the 0.13721 s to reach the line from the grid, gives 188.13389 s. Its distance is clamped to 11 800 m.

**Finish of #1.** Red Bull finishes at 2 · 94.55456 = 189.10913 s. The race becomes `finished` in the step ending at 189.5 s.

**Result.** 1. #2 McLaren, 188.134 s; 2. #1 Red Bull, +0.975 s.

## 7. Design decisions in brief

| Decision | Reason |
|---|---|
| New module `race.py` | Keeps race orchestration out of V0's physics and lap code |
| `RaceCar` as a dataclass | Plain record of identity and state, readable `repr` for debugging |
| Distance as the only progress variable | Laps, positions and gaps can all be derived from it, so nothing can disagree |
| Exact line-crossing time | Results do not depend on `dt` |
| List order = grid order | Simplest deterministic grid; qualifying is out of scope |
| No new dependencies | `bisect`, `dataclasses` and `divmod` are enough |

## 8. Assumptions, simplifications and limitations

1. **Every lap is the V0 flying lap**, including lap 1. There is no standing start. Real lap 1 times would be several seconds slower, and grid position would matter more.
2. **Cars do not interact.** They pass through each other with no blocking, slipstream or overtaking rules. A faster car always gains at its own pace (V3).
3. **No tyres, fuel or pit stops (V2).** Lap times never change during a race.
4. **No chequered-flag rule.** Every car runs the full lap count, including lapped cars (V5).
5. **No weather (V4), no flags, safety car or retirements (V5).**
6. **Grid** is list order with 8 m spacing. There is no qualifying, and the sideways offset is ignored.
7. **Start line = finish line = timing line** at distance 0.
8. **Linear interpolation** inside each ~1 m piece. This is consistent with V0's lap time.
9. **Snapshots happen at step boundaries.** `main.py`'s "After lap 1" table is printed at the first step boundary after the leader crosses the line, so the race clock there is a multiple of `dt`. Finish times are exact; snapshot times are not.
10. **`Race` mutates the `RaceCar`s it is given.** It resets `distance` and `finish_time`. Use fresh `RaceCar`s for each race.
11. **Not validated against real F1.** The simulated Monza lap is about 1:34–1:35, much slower than the fastest real Monza qualifying laps (around 1:19–1:20). The modelled track is 5 900 m against the real 5 793 m. Calibration is V6.
