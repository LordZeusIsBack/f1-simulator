# P2-V3: On-track driving control

Phase 2 milestone 3 of 6. A car can now be **driven by pedals and physics** instead of following a precomputed lap profile. A P2-V2 driving policy's decision changes the controller's target, the controller sets throttle or brake, and the physics integrates the speed and distance. Cars that do not opt in move exactly as before.

Line numbers are from the P2-V3 commit and may shift; symbol names are the stable reference.

## 1. Technical assessment (before this version)

1. **How the lap profile is calculated.** `simulation.simulate_lap` splits the track into ~1 m points (`track_points`), each with (length, radius, gradient, banking). It runs two passes over two laps:
   - a **forward pass** at full throttle: v² = v_prev² + 2·a·ds with `physics.acceleration`, capped at each point's `corner_speed`;
   - a **backward pass** at full braking: v = min(v, √(v_next² + 2·decel·ds)) with `physics.deceleration`.

   The result is the fastest possible speed at every point: full throttle until the last moment, then maximum braking. `race.LapProfile` turns it into cumulative distance and time tables for one tyre grip and fuel load. `lap_profile` caches it, and `Race` rebuilds it at every line crossing and when the track wetness has moved by `WETNESS_STEP`.
2. **How the race moves a car.** `Race._advance` converts the car's distance into "seconds into this lap" on its profile, adds `dt / factor`, and converts back with `LapProfile.distance_at`. Speed is not part of the state: it is whatever the profile says at the new distance. A car released from behind a slower car jumps back to profile speed immediately, with no acceleration.
3. **How driver pace works.** `factor` = `Driver.time_factor()` (pace) × dirty air × DRS, then race control's `pace_factor`. It stretches profile time evenly, so a pace-0 driver is 1 % slower at every point. It is a post-hoc time multiplier, not a change in how the car is driven.
4. **Which controls the physics can represent.** Only longitudinal ones:
   - drive force (engine power ÷ speed, capped by the grip left after cornering);
   - braking force (up to the grip left);
   - drag and gravity;
   - the corner speed limit, including downforce and banking.

   There is no lateral position, so no racing line, no lane and no defensive line can be represented.
5. **The smallest coherent change.** Give selected cars a speed state and move them by integrating throttle and brake through the same force model. Add a controller that sets the pedals from a look-ahead (where it must brake) and from the driver's tactical action. Leave every other car, the profile and the physics module unchanged.

## 2. Scope

**In scope:**
- pedal commands (`Control`), the physics that executes them, and a numerical integrator;
- a braking look-ahead (`BrakingEnvelope`) and a speed controller (`track_speed`);
- a mapping from P2-V2 actions to driving styles (`STYLES`);
- opt-in controlled cars in `Race` (`RaceCar.control`), connected to P2-V2 policies through `driving.run`;
- tests and documentation.

**Out of scope:**
- lateral dynamics, racing lines and lane changes;
- tyre wear that depends on driving;
- physical DRS and dirty-air effects on a controlled car;
- RL training (P2-V4) and changes to wheel-to-wheel rules (P2-V5).

## 3. Architecture: three levels of control

```
P2-V2 tactical policy        policy(DriverObservation, Driver) -> Decision(DriverAction)     every race step (dt, e.g. 0.1 s)
        │  driving.run sets car.control.action
        ▼
P2-V3 controller             STYLES[action] -> grip share u
                             braking_envelope(car, track, grip × u, fuel) -> target speed ahead
                             track_speed(...) -> Control(throttle, brake)                     every sub-step (h = 0.02 s)
        ▼
P2-V3 physics                step_motion(spec, v, point, grip, Control, h) -> (v_new, ds)    every sub-step
                             + Race: corner-limit cap, line crossing, pits, car ahead
```

The levels are kept apart:
- the tactical policy never sees pedals;
- the controller never sees other cars (the race's hold-behind limit does that);
- the physics never sees actions.

They are **not interchangeable**: a tactical decision is "attack now", a controller decision is "brake 53 % this sub-step", and there is no racing-line controller at all.

New code: `control.py` (new module) and a dispatch in `race.py`. Two lines changed in `driving.py`.

| Symbol | Where | Role |
|---|---|---|
| `Control(throttle, brake)` | `control.py:35` | Pedal demands, each 0–1, never both > 0; validated |
| `COAST`, `FULL_THROTTLE`, `FULL_BRAKE` | `control.py:49` | The three corner cases of `Control` |
| `CarControl(action, speed, clipped)` | `control.py:53` | Opts a `RaceCar` in; holds its action, speed (m/s) and clip count |
| `acceleration(...)` | `control.py:60` | m/s² for given pedals |
| `step_motion(...)` | `control.py:69` | One integration sub-step |
| `track_speed(...)` | `control.py:82` | Speed controller: pedals that reach a target speed |
| `BrakingEnvelope`, `braking_envelope` | `control.py:95`, `:135` | Look-ahead: highest speed per point from which every corner ahead can still be made (cached) |
| `STYLES` | `control.py:26` | Grip share per `DriverAction` |
| `CONTROL_STEP`, `MAX_CONTROL_STEP`, `CLIP_TOLERANCE` | `control.py:21-23` | 0.02 s, 0.05 s, 1e-6 m/s |
| `RaceCar.control` | `race.py:49` | `None` (default) = profile movement, as before |
| `Race(control_step=...)` | `race.py:138` | Sub-step for controlled cars, validated (0, 0.05] s |
| `Race._advance_controlled`, `Race._held_speed` | `race.py:426`, `:465` | The controlled movement loop |

## 4. Control equations

All quantities are SI: m, s, m/s, m/s², N, kg.

### 4.1 Pedals
`Control(throttle, brake)`: each value must be an `int` or `float` (not `bool`) with 0 ≤ value ≤ 1. That one check also rejects NaN and ±∞. Pressing both pedals at once raises `ValueError`, because left-foot braking is not modelled.

### 4.2 Forces (`acceleration`, reusing `physics`)
For a car of mass m (car + fuel), at speed v, on a track point with radius r, gradient g (%), banking b and tyre grip μ:

```
F_grip  = physics.longitudinal_grip(spec, v, r, μ, b)       N left for driving/braking after cornering (friction circle)
F_drive = throttle × min(power / max(v, 1), F_grip)          N, power-limited, grip-limited
F_brake = brake × F_grip                                     N
F_drag  = physics.aero(drag, v) = ½ ρ C_d v²                 N
a       = (F_drive − F_brake − F_drag) / m − G × g / 100     m/s²
```

- With `throttle = 1` this is exactly `physics.acceleration`.
- With `brake = 1` it is a full stop. The gravity term has the physically correct sign: braking uphill is helped and braking downhill is hindered.
- **Pre-existing inconsistency found:** `physics.deceleration`, used by the profile's backward pass since V0, *subtracts* G·g/100. That models braking uphill as weaker, which is the wrong sign. P2-V3 does not change it, so all V0–V9 results stay identical. Fixing it would change every recorded lap time and the V6/V9 calibration, so it should be done as a separate, deliberate change. It only matters where braking zones have a gradient.

### 4.3 Numerical update (`step_motion`)
For one sub-step of h seconds at the point the car is on:

```
v_new = max(0, v + a(v) × h)          explicit Euler on speed; floored at 0: no reversing, no rolling back
ds    = (v + v_new) / 2 × h           trapezoid on distance
```

- For constant acceleration this pair is exact: v_new² = v² + 2·a·ds, the same relation the profile uses.
- The error comes only from evaluating a at the start of the sub-step and from using the point the car starts on.
- `step_motion` rejects h outside (0, `MAX_CONTROL_STEP`] and a negative, NaN or infinite speed.

### 4.4 Corner limit
After each sub-step, `Race._advance_controlled` compares v_new with `physics.corner_speed` at the point reached, using the **real** tyre grip.
- A 1-D model cannot leave the track, so the speed is capped there.
- If the excess is more than `CLIP_TOLERANCE` (1e-6 m/s, to ignore float rounding), `CarControl.clipped` counts it.
- A well-driven car scores 0. Section 9 lists when it does not.

## 5. Braking look-ahead (`BrakingEnvelope`)

A car at a single track point cannot know where to brake, so the controller needs a look-ahead. Positions and speeds alone don't provide one; the profile's speed trace does, but it is built with the inconsistent `physics.deceleration` and at full grip only.

`BrakingEnvelope(car, track, μ_plan, fuel)` (`control.py:95`) stores, for every track point, the highest speed from which the car can still slow for every corner ahead:
1. Start from each point's corner limit `corner_speed(spec, r, μ_plan, b)`.
2. Go **backwards** around two laps (so the start/finish line wraps): v_i = min(limit_i, √(v_{i+1}² + 2·B·ds)), where B is the full-brake deceleration from `acceleration`.
3. B depends on the speed it is evaluated at (more speed means more downforce but also more cornering load), so `_entry` evaluates it twice: once at v_{i+1} and once at that first estimate. It keeps the **lower** result. Near a corner limit the friction circle changes sharply, the two estimates fall on either side of the exact value, and the lower one is the safe one.

Without step 3, the car clipped about 0.3 m/s at a mid-corner radius change at Spa. A two-pass version that kept the second estimate clipped hundreds of times at Interlagos, whose Esses have a −23.9 % gradient in the V9 data. There, gravity alone overcomes full braking at the corner limit, so the car has to enter below it.

`target(x)` returns the lower of the two points around x, so a braking point is never skipped between points. `point(x)` gives the track point. `braking_envelope` caches envelopes like `race.lap_profile`. A Monza envelope takes 0.19 s to build, against 0.15 s for `simulate_lap`. A new one is needed when the grip, fuel or action changes (in practice, at each lap and each action switch).

## 6. The controller (`track_speed`) and the styles

**Target.** In each sub-step the car aims for the envelope one sub-step ahead, divided by the race's factor:
```
target = envelope.target(lap_distance + v × h) / factor
```
- The envelope uses the planned grip `μ_plan` = real grip × `STYLES[action]`.
- `factor` is the same factor `Race` computes for every car (pace, dirty air in corners, DRS on straights, race control). So pace, dirty air, VSC, SC and yellows still slow a controlled car, but through its **target**, and the car reaches that target through physics.

**Pedals.** `a` is linear in each pedal, so the exact demand is:
```
needed = (target − v) / h
coast  = a(COAST)
if needed ≥ coast:  throttle = min(1, (needed − coast) / (a(FULL_THROTTLE) − coast))
else:               brake    = min(1, (coast − needed) / (coast − a(FULL_BRAKE)))
```
- A reachable target is hit exactly in one sub-step (`test_speed_controller_matches_reachable_targets`).
- An unreachable target saturates the pedal at 1.
- This is inverse dynamics, not a tuned PID controller: there are no gains to tune.

**Styles** (`STYLES`, placeholders):

| Action | Grip share u | Effect on motion |
|---|---|---|
| `ATTACK` | 1.00 | At the limit: corner speeds and braking at full grip |
| `DEFEND` | 1.00 | Same as attack. With no lateral model, defending can only mean pushing to keep the gap. **No defensive line is modelled** |
| `MAINTAIN_PACE` | 0.97 | 3 % grip margin: lower corner speeds, earlier braking |
| `CONSERVE_TYRES` | 0.90 | 10 % margin: slower still. **Tyre wear does not depend on it yet** (still `laps × wear_per_lap`) |

At u < 1 the corner targets are `corner_speed` at u·μ, and braking is planned at u times the grip, so there is a real margin. Straights are always full throttle: the envelope there is far above top speed.

Measured on the test track `Stadium` (2 laps, the test car `FAST`, no wear or fuel burn):
- minimum speed in the 50 m corners: 34.087 m/s (ATTACK), 33.436 (MAINTAIN) and 31.857 (CONSERVE; exactly `corner_speed` at 0.9 μ);
- finish times: 47.958 s, 48.501 s and 49.922 s.

## 7. Integration with `Race`

`RaceCar(..., control=CarControl())` opts a car in. Everything else about `Race` is unchanged:

- **`Race.__init__`**: a controlled car starts at its profile's speed at its grid slot. That is a flying start, the same as every other car.
- **`Race._advance`** passes a controlled car to `_advance_controlled` with the same `end`, `factor` and `limit` arguments. Every caller in `step` and `_drive` (traffic on or off, race control or not) therefore works unchanged.
- **`_advance_controlled`** loop (`race.py:426`), until race time `end`:
  1. Wait in the pits until `pit_exit`. The speed is kept: the pit loss already covers the whole stop.
  2. h = min(`control_step`, time left).
  3. Mass = car + fuel; grip = `car.tyres.grip(compounds, wetness)`; envelope for grip × `STYLES[action]`.
  4. Pedals from `track_speed`, then `step_motion`, then the corner-limit cap and count.
  5. **Car ahead:** if the new distance passes `limit` (held behind, or the SC queue gap), the car stops at `limit` at no more than the car ahead's speed (`_held_speed`).
  6. **Line:** if the new distance reaches the line, the crossing time is interpolated within the sub-step, the car is placed on the line, and `_complete_lap` runs (fuel, tyres, pit stops, finish, penalties), as in `_advance`.
- **`_free_distance`** (would the car reach the car ahead this step?) and **`_speed`** (speed for the overtaking rule) use the controlled car's actual speed. So `OvertakeEvent.advantage` and `driving.observe(...).speed` report what the car is really doing.
- **`interval`** (time gaps, DRS detection) still uses the car's reference profile. That is an estimate for a controlled car.
- **`driving.run`** now copies each decision into `car.control.action` for controlled cars. For uncontrolled cars decisions are still only logged.
- **Availability still applies.** `ATTACK` needs a car ahead (P2-V2 `available_actions`), so a car alone in front can use only `MAINTAIN_PACE` or `CONSERVE_TYRES` through a policy. Code may still set `car.control.action` directly; tests do, and P2-V4 may.

**The strategist** (`rl/env.py`) creates no controlled cars and is unchanged. Its pit actions remain pit actions.

## 8. Time step selection

The race step `dt` sets how often policies decide. `control_step` sets the physics sub-step. Measured with an `ATTACK` McLaren alone, 2 laps on each of the 28 circuits, compared with `simulate_lap`:

| `control_step` | Lap time vs profile | Clipped sub-steps (all circuits) | Monza, wall time per lap |
|---|---|---|---|
| 0.005 s | +0.01 % to +0.19 % | 36 (Interlagos 30, Istanbul 6) | ~0.3 s |
| **0.02 s (default)** | +0.05 % to +0.28 % | 6 (Interlagos 5, Istanbul 1) | ~0.08 s |
| 0.05 s (maximum) | +0.08 % to +0.52 % | 5 (Suzuka 2, COTA 2, Zandvoort 1) | ~0.05 s |

- **At 0.005 s and 0.02 s every clip is under 0.05 m/s** (none are counted at a 0.05 m/s threshold). All of them are on the steep downhill corners described in §5.
- **At 0.05 s the clips are larger:** between 0.2 and 0.5 m/s at Suzuka, and between 0.1 and 0.2 m/s at COTA. The look-ahead of one sub-step (4.5 m) is then too coarse for some corner entries. This is one reason the default is 0.02 s.
- At 90 m/s, 0.02 s is 1.8 m, close to the 1 m track resolution. 0.05 s is 4.5 m, where braking points start to smear (the +0.5 %). Above 0.05 s the error would grow further, so `Race` and `step_motion` reject it.
- **The race step barely matters:** on Stadium, changing `dt` from 0.02 s to 1.0 s moves the finish time by less than 2·10⁻⁵ s.
- The controlled car is slightly slower than the profile because the profile is the ideal envelope and the controller reaches it one sub-step late.

## 9. Assumptions, limitations and known weaknesses

- **No lateral model.** There is no racing line, lane, side-by-side running or defensive weaving. `DEFEND` drives exactly like `ATTACK`.
- **`CONSERVE_TYRES` has a cost but no benefit.** It is slower, but wear is still per lap. Before an RL driver is trained (P2-V4), wear must depend on how hard the car is driven, or a learner will simply never conserve. (Done in P2-V4 for controlled cars.)
- **DRS and dirty air act on the target only.** A controlled car is already at full throttle on straights, so DRS gives it nothing. Dirty air lowers its corner target. Physical versions (less drag, less downforce) are not modelled.
  - **Correction (P2-V4):** the DRS part was not true in P2-V3. Dividing the target by the DRS factor (0.965) also raised it in the braking zone at the end of the straight, so the car braked too late and the corner cap removed the excess for free. P2-V4 divides by `max(factor, 1)`, which makes the statement true. See [P2-V4 IMPLEMENTATION.md §3.2](../p2-v4/IMPLEMENTATION.md#32-bug-fix-drs-let-a-controlled-car-brake-too-late-p2-v3).
- **Held behind a car:** the controlled car is placed at the limit and its speed capped at the car ahead's. For an uncontrolled car ahead, that speed is its profile speed ÷ its pace, ignoring its flags and dirty air.
- **Mixed fields.** Profile cars still "teleport" back to profile speed after being held up, while controlled cars accelerate through physics. In mixed races that is a small disadvantage for controlled cars.
- **Clips can still occur:**
  - on the steepest downhill corners in the V9 data (§8), under 0.05 m/s at the default sub-step;
  - at the largest sub-step (0.05 s), up to about 0.5 m/s at some corner entries (§8);
  - when the grip drops in one go because the track wetness passed `WETNESS_STEP` (a real slide, counted). A wet test race showed 4 such clips.
- **Flying start, and speed kept through pit stops,** as for profile cars. There is no standing start or pit-lane speed limit.
- **The pedal command is not stored.** `CarControl` keeps only action, speed and clip count. To see pedals, call `track_speed` yourself (CODE_FLOW.md §5).
- **Floating-point remainder:** five 0.02 s sub-steps do not add up to exactly 0.1 s in binary, so a race step of 0.1 s ends with a sub-step of about 10⁻¹⁷ s. It is harmless.
- **Placeholder numbers:** `STYLES`, `CONTROL_STEP` and `MAX_CONTROL_STEP` are chosen, not measured. The forces themselves come from the unchanged V0 physics, with its simplifications (for example, braking near 7–8 g at Monza's top speed).

## 10. Worked example (Monza, 4 laps)

> **Correction (P2-V4):** the aggressive policy's pass in this table relied on the DRS bug described in §9. With the fix, none of the four policies passes and the times are 382.342 / 382.342 / 381.930 / 381.629 s (README). The braking trace in CODE_FLOW.md is on lap 2, before DRS is enabled, but it shifts slightly: P2-V4's driving-dependent wear leaves the tyres less worn after lap 1 (grip 1.7973 instead of 1.79676), and the traced step ends at 93.994 m/s instead of 93.970.

A Ferrari driven by its profile leads a McLaren with `CarControl()`. Both drivers are default and fictional ("Leader", "Chaser"). Only the McLaren's policy changes (README example):

| McLaren policy | McLaren finish | Passed the Ferrari? | Action switches |
|---|---|---|---|
| steady (always `MAINTAIN_PACE`) | 382.302 s | never | MAINTAIN 1 |
| `CONSERVATIVE` | 382.302 s | never | ATTACK 1, MAINTAIN 1 |
| `BALANCED` | 381.685 s | never | ATTACK 21, MAINTAIN 21 |
| `AGGRESSIVE` | 380.498 s | at 204.7 s | ATTACK 31, DEFEND 1, MAINTAIN 31 |

- The more often a policy chooses `ATTACK`, the more time the McLaren spends at full grip, and the faster it is.
- Only the aggressive policy attacks often enough to get the speed advantage the race's passing rule requires (2.0 m/s between default drivers). It passes on lap 3, with DRS (+5.94 m/s).
- The conservative policy's one `ATTACK` changed nothing measurable: the McLaren was held behind the Ferrari at that moment.

One braking sub-step of this race (CODE_FLOW.md §4 has the full trace) happens at 107.9 s, 1,093.8 m into lap 2, 116 m before the first corner:
- v = 97.900 m/s; the target 1.96 m ahead is 96.987 m/s;
- needed = −45.65 m/s²; coasting gives −9.035 and full brake −77.718, so brake = (−9.035 + 45.65) / (−9.035 + 77.718) = **0.533**;
- `step_motion` gives v_new = 96.987 m/s and ds = 1.949 m.

## 11. Why this is a suitable foundation for P2-V4

- A driving RL environment can act at the tactical level (`car.control.action` per decision step, as `driving.run` does) or later at the pedal level (`Control`). Both levels execute through the same physics.
- Motion is deterministic, bounded and validated. The time step is documented and stable, and a race of controlled cars costs about 0.08 s per car-lap at Monza.
- `CarControl.clipped` is a ready-made signal for "drove past the limit", for example as a penalty.
- **What P2-V4 must add first:** a reason to drive below the limit, meaning wear (or risk) that depends on the grip share. Without it, maximum attack is always optimal and nothing is learned.
