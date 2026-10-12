# V4: Weather and changing track conditions (implementation)

## 1. Objective and scope

Up to V3 the track was always dry and identical from start to finish. In V4:

- a scripted **weather timeline** sets air temperature and rain over race time;
- the track's **wetness** rises in rain and falls as the track dries;
- wetness reduces **tyre grip**, by much more for slicks than for intermediates and wets, so the most suitable compound changes as the track gets wetter or drier;
- the race logs rain starting or stopping and changes of the most suitable compound;
- a strategy can opt in to **react to the weather** by pitting for the most suitable tyres.

Not in scope, and not implemented: realistic rain forecasting, a CFD or spray model, tyre thermal models, an RL weather policy, a wetness that varies around the lap, and race-control responses to rain (safety car, DRS disabled), which belong to V5.

**All weather parameters are placeholders.** They were chosen so the effects are visible and plausible in order of magnitude. The model does **not** reproduce real F1 wet-weather performance.

## 2. What was added or changed

| Item | Where | New / changed |
|---|---|---|
| `WeatherPoint`, `Conditions`, `Weather` and constants | `weather.py` | **new**: the weather model |
| `Compound.wet_loss` | `tyres.py` | new field (default 0.0) |
| `DRY_COMPOUNDS`, `COMPOUNDS` | `tyres.py` | `DRY_COMPOUNDS` is V2's table plus `wet_loss`. `COMPOUNDS` adds INTERMEDIATE and WET. |
| `Tyres.grip(compounds, wetness=0.0)` | `tyres.py` | changed: × (1 − wet_loss × wetness) |
| `best_compound(compounds, wetness)` | `tyres.py` | new: tyre suitability |
| `Strategy.react_to_weather`, `planned_stop()`, `stop_after(lap, tyres, wetness, compounds)`, `WEATHER_MARGIN` | `strategy.py` | new and changed |
| `Race(weather=None)`, `weather_events`, `WeatherEvent`, `WETNESS_STEP`, `_update_weather` | `race.py` | new |
| `Race.step`, `_profile`, `_complete_lap`, `_check` | `race.py` | changed: weather update, profile refresh, weather-aware strategy call |

## 3. Who owns what

```
weather.py   Weather: timeline + wetness state → Conditions         knows nothing about cars or physics
tyres.py     how wetness changes a compound's grip; best compound    knows nothing about time or the race
strategy.py  whether a car should pit for other tyres                reads wetness, tyres, compounds
race.py      when the weather advances, when grip is recomputed,     orchestration and logs
             when the strategy is asked, the event log
physics.py   unchanged: it still receives one grip coefficient per profile
```

The V0 physics is **not** touched. Wet weather reaches it only through the single `tyre_grip` number it already accepted in V2.

## 4. State variables

| Variable | Unit | Allowed range | Kind | Where |
|---|---|---|---|---|
| `time` | s | ≥ 0 | race clock (advanced by the race) | `Weather.time`, `Conditions.time` |
| `air_temp` | °C | −10 to 50 | **scripted** (timeline, interpolated) | `WeatherPoint.air_temp`, `Conditions.air_temp` |
| `rain` (precipitation) | mm/h | 0 to 50 | **scripted** (timeline, interpolated) | `WeatherPoint.rain`, `Conditions.rain` |
| `wetness` | dimensionless | 0 (dry) to 1 (fully wet, standing water) | **integrated state** | `Weather.wetness`, `Conditions.wetness` |
| `track_temp` | °C | −10 to 65 (follows from the ranges above) | **derived** | `Conditions.track_temp` |

Validation (`ValueError`):

- a `WeatherPoint` with `time < 0`, `air_temp` outside −10 to 50 °C, `rain` outside 0 to 50 mm/h, or a NaN value;
- an empty timeline, or times that are not strictly increasing;
- a starting `wetness` outside 0 to 1;
- a `Weather` that has already been advanced being given to a new `Race`.

## 5. Scripted timeline

A timeline is a list of `WeatherPoint(time, air_temp, rain)` keyframes.

- Between two keyframes, air temperature and rain change **linearly**.
- Before the first keyframe its values hold; after the last keyframe its values hold.
- An abrupt change is scripted explicitly, by putting two keyframes close together. For example, rain going from 0 to 6 mm/h between 500 s and 560 s is a one-minute build-up.

Rain may change as abruptly as the script says. **Wetness never jumps**: it follows the equation below.

## 6. How wetness evolves

### 6.1 Equation

```
k_wet = WETTING_RATE × rain                                     1/s      (WETTING_RATE = 0.001 per mm/h)
k_dry = DRYING_RATE × max(0, track_temp − DRYING_MIN_TEMP)      1/s      (DRYING_RATE = 3·10⁻⁵ per °C, DRYING_MIN_TEMP = 0 °C)

dW/dt = k_wet × (1 − W)  −  k_dry × W
```

- **Rain** wets the part of the track that is still dry, so W can approach but never pass 1.
- **Drying** removes a share of the existing water per second. It is faster on a warmer track and stops at or below 0 °C. Freezing is not modelled.
- Both act all the time. Under steady rain, W settles where they balance:

  ```
  W* = k_wet / (k_wet + k_dry)
  ```

### 6.2 Update

`Weather.advance(dt)` freezes the rates at their values at the start of the step and applies the exact solution for constant rates:

```
W(t + dt) = W* + (W(t) − W*) × e^(−(k_wet + k_dry) × dt)
```

This is stable for any `dt`, cannot overshoot 0 or 1, and moves smoothly. If both rates are 0 (no rain and a track at 0 °C or colder), W does not change.

### 6.3 Magnitudes (model output)

With 25 °C air and a 4 mm/h shower starting on a dry track:

| Time after the rain starts | 100 s | 200 s | 300 s | 500 s |
|---|---|---|---|---|
| Wetness | 0.31 | 0.50 | 0.62 | 0.75 |

After the rain stops (from W = 0.78), the track takes about 700 s to fall back to W = 0.40, where slicks are the best tyre again. It is down to about 0.07 after 2 300 s.

Heavy rain (50 mm/h) brings the track close to fully wet within about a minute. The largest possible change in one 0.1 s step is k_wet × 0.1 = 0.005.

### 6.4 Track temperature

```
track_temp = air_temp + SUN_HEATING × (1 − W)          SUN_HEATING = 15 °C
```

A dry track is 15 °C warmer than the air; a fully wet track is at air temperature. Track temperature therefore falls as the track gets wet, and recovers as it dries, smoothly because W is smooth.

In V4, track temperature affects **only the drying rate**. It has no direct grip effect: there is no tyre temperature model, which the brief excludes.

## 7. From wetness to grip and lap time

Each compound now has a `wet_loss` value: the fraction of its grip lost on a fully wet track.

```
grip = μ₀ × (1 − WORN_GRIP_LOSS × wear) × (1 − wet_loss × W)
```

The first two factors are V2's. The last is new, and equals 1 on a dry track.

| Compound | μ₀ (dry, new) | wear / lap | wet_loss | Grip at W = 0 / 0.25 / 0.5 / 0.75 / 1 |
|---|---|---|---|---|
| SOFT | 1.83 | 0.05 | 0.65 | 1.830 / 1.533 / 1.235 / 0.938 / 0.640 |
| MEDIUM | 1.80 | 0.03 | 0.65 | 1.800 / 1.508 / 1.215 / 0.922 / 0.630 |
| HARD | 1.775 | 0.02 | 0.65 | 1.775 / 1.487 / 1.198 / 0.910 / 0.621 |
| INTERMEDIATE | 1.55 | 0.03 | 0.32 | 1.550 / 1.426 / 1.302 / 1.178 / 1.054 |
| WET | 1.35 | 0.03 | 0.15 | 1.350 / 1.299 / 1.249 / 1.198 / 1.147 |

The assumptions behind these values (placeholders, not Pirelli data):

- **Slicks** have the most grip when dry, but lose it fastest as water builds up: they cannot clear it.
- **Intermediates** are a compromise: less dry grip, but much less sensitive to water.
- **Wets** have the lowest dry grip and the smallest loss.
- A wear rate of 0.03/lap for inters and wets is a placeholder. Wear does not depend on wetness: overheating on a drying track is not modelled.

The grip goes to `simulate_lap` exactly as in V2. Lap times for the McLaren at Monza with new tyres and no fuel (model output):

| W | Soft | Medium | Hard | Inter | Wet |
|---|---|---|---|---|---|
| 0.0 | **93.43** | 94.00 | 94.48 | 99.36 | 104.73 |
| 0.2 | **98.37** | 98.98 | 99.49 | 101.87 | 105.99 |
| 0.4 | **104.60** | 105.28 | 105.86 | 104.68 | 107.31 |
| 0.6 | 113.11 | 113.91 | 114.59 | **107.88** | 108.72 |
| 0.8 | 125.83 | 126.81 | 127.65 | 111.58 | **110.22** |
| 1.0 | 148.60 | 149.99 | 151.18 | 115.92 | **111.81** |

**Affecting cars differently.** At W = 0.8 a car on slicks is about 15–17 s/lap slower than a car on wets. On a dry track the order reverses by about 11 s/lap.

## 8. Tyre suitability

```
best_compound(compounds, W) = the compound whose new set has the most grip at W   (table order breaks a tie)
```

Wear is ignored on purpose: the question is which **type** of tyre suits the track, not which particular set. The crossovers follow from the linear model, `W = (μa − μb) / (μa·la − μb·lb)`:

| Equal grip | W |
|---|---|
| soft = intermediate | **0.404** |
| medium = intermediate | 0.371 |
| hard = intermediate | 0.342 |
| intermediate = wet | **0.681** |

With the default table, the best compound is:

- SOFT for W < 0.404;
- INTERMEDIATE for 0.404 to 0.681;
- WET above 0.681.

A race given only `DRY_COMPOUNDS` always picks a slick.

## 9. Weather-aware strategy

`Strategy(..., react_to_weather=True)` keeps V2's planned stops. At every line crossing that has no planned stop, `stop_after(lap, tyres, wetness, compounds)` does this:

```
best = best_compound(compounds, wetness)
pit for `best`  if  grip(new best set) > grip(new set of current compound) × (1 + WEATHER_MARGIN)      WEATHER_MARGIN = 0.05
```

The 5 % margin stops a car pitting for a marginal gain right at a crossover, and stops it switching back and forth. With the default table the switching points are:

| On | Switch to | When |
|---|---|---|
| medium | intermediate | W > 0.464 |
| intermediate | wet | W > 0.872 |
| wet | intermediate | W < 0.468 |
| intermediate | soft | W < 0.303 |

Weather stops add no fuel, so V2's fuel check, which uses only planned stops through `planned_stop()`, still holds. They always fit a compound from the race's table, and they always change the compound, so they are valid by construction. A plan without `react_to_weather` ignores the weather, exactly as in V2.

## 10. Update sequence inside one race step

`Race.step(dt)` with `weather` set:

1. **Refresh grip if the track changed.** If `|W − W_grip| ≥ WETNESS_STEP (0.05)`, set `W_grip = W` and rebuild every running car's lap profile now, mid-lap. `W_grip` is the wetness the current profiles were built for.
2. **Move the cars** with V3's logic: traffic, `_advance`, line crossings. At a line crossing, the new lap's profile uses `W_grip`, and the strategy is asked with the **current** wetness `W`.
3. **Advance the weather** by `dt` (§6.2).
4. **Log events**, stamped with the end of the step:
   - `"rain starts"` or `"rain stops"` when rain changes between 0 and more than 0;
   - `"best tyres"` when `best_compound` at the new W differs from the old W.

   Each `WeatherEvent` stores the new `Conditions` and the best compound.
5. `race.time = end`.

With `weather=None`, steps 1, 3 and 4 do nothing. The wetness used for grip is 0, so the race is V3's exactly. A dry timeline (no rain) also gives the same result as `weather=None`; a test checks this.

**Why rebuild mid-lap?** Profiles are otherwise built once per lap (V2). A shower that starts mid-lap would then not affect anyone until the line. Rebuilding every 0.05 of wetness keeps grip within 0.05 of the track. In the README race that means 26 rebuild points over 20 laps, at about 35 ms per car each. The car keeps its position, and its speed switches to the new profile's speed at that point.

## 11. Worked example: a dry race becomes wet

This is the README race: 20 laps of Monza, traffic on, two identical McLarens on mediums.

- #1 "stays out" has a fixed plan with no stops.
- #2 "reacts" has `react_to_weather=True`.

The timeline:

- 24 °C and dry until 500 s;
- rain builds to 6 mm/h by 560 s while the air cools to 21 °C;
- the rain holds until 1 100 s (air 19 °C), then stops by 1 160 s;
- the air warms to 22 °C by 2 000 s.

| Lap done (approx. time) | W | Best | #1 tyres, grip, next-lap time (s) | #2 tyres, grip, next-lap time (s) |
|---|---|---|---|---|
| 5 (474 s) | 0.00 | soft | medium, 1.784, 94.94 | medium, 1.784, 94.94 |
| 6 (571 s) | 0.21 | soft | medium, 1.536, 99.96 | medium, 1.533, 99.96 |
| 7 (677 s) | 0.55 | **intermediate** (since 621 s) | medium, 1.137, 112.62 | **pits → intermediate**, 1.274, 107.57 |
| 9 (920 s) | 0.83 | **wet** (since 749 s) | medium, 0.818, 128.39 | intermediate, 1.135, 112.21 |
| 11 (1 146–1 184 s) | 0.86–0.88 | wet | medium, 0.782, 133.02 | **pits → wet** (W 0.876 > 0.872), 1.173, 110.96 |
| 14 (1 499–1 564 s) | 0.66–0.69 | intermediate (since 1 513 s) | medium, 1.007, 121.37 | wet, 1.204, 109.95 |
| 18–19 (2 020–2 045 s) | 0.44–0.45 | intermediate | medium, 1.236, 108.76 | **pits → intermediate** after lap 19 (W 0.437 < 0.468) |
| 20 (finish) | 0.37–0.39 | **soft** (since 2 130 s) | finishes 2 235.413 s | finishes **2 172.144 s** |

What happens:

1. **Dry phase.** Both cars do about 94.9 s laps.
2. **Rain starts at 500 s.** W rises; the track temperature drops from 39 °C towards the air temperature. Grip is refreshed every 0.05 of W.
3. **Slicks lose most.** By lap 7 the best compound is intermediate. #1 stays out and laps in 106–133 s.
4. **#2 reacts.** It pits for inters after lap 7, once W is above 0.464, and for wets after lap 11, once W is above 0.872. Apart from the laps that include a stop, its laps stay at 108–113 s.
5. **Rain stops at 1 160 s.** The track dries: best becomes intermediate at 1 513 s and soft at 2 130 s.
6. **A weakness of the policy.** #2 pits back to inters after lap 19 of 20, a stop that cannot pay back in one lap, because the rule ignores the laps remaining.

#2 still wins by 63 s.

Weather events logged:

```
 500.0 s  rain starts  wetness 0.00  best soft
 621.0 s  best tyres   wetness 0.40  best intermediate
 748.6 s  best tyres   wetness 0.68  best wet
1160.0 s  rain stops   wetness 0.87  best wet
1513.0 s  best tyres   wetness 0.68  best intermediate
2129.9 s  best tyres   wetness 0.40  best soft
```

## 12. Assumptions and limitations

1. **One wetness for the whole track.** There are no puddles, no drying line and no spray.
2. **Rain has no direct effect** on aerodynamics, visibility, dirty air or DRS. DRS is still allowed in the wet; real race control would disable it (V5).
3. **Track temperature only changes the drying rate.** There are no tyre temperatures and no cold-tyre warm-up.
4. **Inters and wets do not overheat or wear faster on a drying track.** They only have less grip.
5. **The weather policy is simple:** best compound plus a 5 % margin. It ignores laps remaining, pit loss and traffic, and can make stops that do not pay off (§11).
6. **Grip lags the track by up to `WETNESS_STEP = 0.05`.** At a rebuild, the car's speed switches to the new profile's speed at that point.
7. **Rates are frozen for each step.** This makes a tiny `dt` dependence (0.1 s steps against time constants of a minute or more). Event times have `dt` resolution.
8. **Every value is a placeholder:** wetting, drying, sun heating, `wet_loss`, μ₀ of inters and wets, and the margin (calibration is V6).
9. **The timeline is fully scripted.** There is no forecast uncertainty and no randomness.
