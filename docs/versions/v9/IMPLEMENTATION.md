# V9: Real circuits, richer track geometry and randomised race conditions (implementation)

## 1. Objective and scope

V9 was requested after the planned roadmap (V0–V8) was complete. The request:

1. Add the major real circuits: Sepang, Baku, Singapore, Buddh, COTA, Imola and others. Use [F1-Encyclopedia](https://github.com/LordZeusIsBack/F1-Encyclopedia) by LordZeusIsBack as the source.
2. Describe tracks with more than straights and corners: chicanes, hairpins, spirals and so on.
3. Correct the V7/V8 problems reported after V8:
   - the RL environment used the uncalibrated model;
   - the race settings were fixed placeholders.

   Settings such as fuel use, VSC and weather should be random, unknown to the agent beforehand, and should change how the race goes.
4. Keep the code open source, solve the data-licensing problem if possible, and credit the people who created the data.

**Out of scope, unchanged:**
- the car models and drivers;
- traffic, weather physics and race-control rules;
- the simulator's default constants (`TYRE_GRIP` 1.8, `PIT_LOSS` 22 s, `FUEL_PER_LAP` 1.9 kg);
- the V8 research question and its decision rule.

No dependencies were added.

## 2. Source data and how far it can be trusted

F1-Encyclopedia is a set of Markdown files. For this work it provides:

| What | Where | Used for |
|---|---|---|
| Lap length, race laps, corner count, lap record | 15–17 (circuit entries), 05 §1 | `official_length`, `laps`, `lap_record` |
| Corner-by-corner descriptions with **[Estimate]** entry and minimum speeds | 15–17 | Corner minimum speeds (lines marked `# E` in `tracks.py`, 148 lines) |
| Speed classification table: minimum-speed class, lateral g | 03 §2 | Corner radius from speed (`radius_for`) |
| Corner taxonomy: hairpin, chicane, esses, decreasing/increasing radius, spiral, banked, off-camber | 03 §3 | The new segment types |
| Longest straights, elevation changes | 20 §4, §6 | Straight lengths and elevation for some circuits |
| Pit loss of ~20–25 s, circuit-dependent | 12 §16.5 | Generic pit loss 22.5 s ± 2.5 s |
| Street circuits ("safety car period very likely"), wet-prone circuits, tyre-demanding circuits | 20 §9, §15.1, §15.13 | Per-circuit randomisation settings |
| 110 kg race fuel limit | 04, 14 | Upper bound for the fuel assumption |

**Limits of the source:**
- It gives **no corner radii and no straight lengths**, except the longest straight on six circuits. Many corners have no speed.
- Some values are wrong or inconsistent:
  - Imola's lap record is not the current layout's;
  - the COTA and Las Vegas record holders are wrong (the times are right);
  - corner numbering at the Red Bull Ring and COTA does not match the layouts;
  - Singapore's record is for an older layout.
- Sepang, Buddh and Istanbul have almost no data, and Madrid (2026) postdates its author's knowledge.

**Gaps were filled from Wikipedia**, which was checked for each value:

| Circuit | Values taken from Wikipedia |
|---|---|
| Sepang | Length 5.543 km, 15 turns, record 1:34.080 |
| Buddh | Length 5.125 km, 16 turns, record 1:27.249 |
| Madrid | Length 5.414 km, 22 turns, La Monumental banking capped at 13.5°, 2026 record 1:35.587 |
| Zandvoort | Banking: 19° at T3, 18° at T14 |
| Imola, Monaco | Current-layout lap records |
| Singapore (2023–24 layout) | Lap record |

Every such value is noted on its class in `tracks.py`. Race laps for Sepang, Buddh, Istanbul and Madrid follow the F1 rule: the fewest laps that exceed 305 km. A test checks that rule on every circuit except Monaco.

**Everything else is an estimate by the V9 author (Claude), not measured:**
- unmarked corner speeds;
- all turn angles and estimated straight lengths;
- Jeddah's 12° Turn 13 banking.

## 3. Track geometry (`abstract_classes.py`, `simulation.py`)

The lap model drives the track as a list of ~1 m points with (length, radius, gradient). V9 adds **banking**, and lets each segment decide its own points through `TrackSegment.points(step)`.

| Class | Parameters | Points |
|---|---|---|
| `TrackSegment` / `Straight` / `Corner` | length, radius, gradient, `banking=0.0` | `max(1, round(length / step))` equal points: exactly V0's cut |
| `Hairpin(Corner)` | radius, gradient, angle=180°, banking | As a corner; length = radius × angle |
| `Spiral(Corner)` | length, entry radius, exit radius | Curvature 1/r is linear in distance (an Euler spiral), sampled at each point's middle. `math.inf` at one end gives a transition from a straight. `radius` is the tighter end. |
| `Chicane(TrackSegment)` | two or more parts | The parts' points in order; radius = tightest part; gradient = length-weighted mean |
| `Esses(Chicane)` | two or more parts | Same as a chicane; the name follows the encyclopedia's taxonomy (fast S-bends) |

**Why these types:**
- **Spiral:** a varying radius changes the speed limit along the corner, which a constant-radius `Corner` cannot do. It is used for Parabolica, Shanghai T1–T2 and T12–T13, Istanbul T8, COTA T16–T18 and Buddh T10–T11.
- **Chicane and Esses:** turn a multi-corner complex into one segment, so race control and traffic treat it as one place. It is never a straight, so there is no overtaking or DRS inside it.
- **Direction:** left or right does not matter in a one-dimensional model, so it is not stored.
- **Not modelled:** crests and compressions (vertical curvature), and track width. Corkscrews are a chicane plus a gradient.

### 3.1 Banking (`physics.py`)

On a road banked by angle b, the normal force also supplies part of the centripetal force. With grip μ, downforce coefficient k = μ·½ρ·C_L·A, and mass m:

- Lateral force needed in the road plane: m·v²/r·cos b − m·g·sin b.
- Normal force: m·g·cos b + m·v²/r·sin b + ½ρ·C_L·A·v².
- **Corner speed:** v² = (μ cos b + sin b)·m·g / (m/r·(cos b − μ sin b) − k). If the denominator is ≤ 0 there is no grip limit.
- **Longitudinal grip** (friction circle): √((μN)² − lateral²).

**At b = 0 every expression is bit-identical to V0:**
- `_tilt(0)` returns exactly (1.0, 0.0);
- multiplying by 1.0 and adding 0.0 are exact in IEEE arithmetic;
- the factor order is unchanged.

All V0–V5 regression tests still pass with exact or 1e-12 tolerance. Negative banking is off-camber. Lap simulation is about 8 % slower: 35 ms against 32 ms for one Monza lap.

## 4. Circuits (`tracks.py`)

`Circuit(Track)` holds a circuit's metadata as class attributes:
- `official_length`, `laps`, `lap_record`;
- `rain_chance`, `neutralisation_chance`, `pit_loss`, `tyre_wear` (used by the RL environment).

`layout()` returns segments from the start/finish line. Corners are built from speeds:

- **`radius_for(speed)`:** v² / (g·G), where G is interpolated linearly between the middles of the encyclopedia's speed classes:

  | Class | Minimum speed (km/h) | Lateral g |
  |---|---|---|
  | Ultra-slow | 62.5 | 2.0 |
  | Slow | 87.5 | 2.5 |
  | Medium-slow | 115 | 3.0 |
  | Medium | 145 | 3.6 |
  | Medium-fast | 180 | 4.25 |
  | Fast | 225 | 5.0 |
  | Ultra-fast | 275 | 5.75 |

  G is held constant outside that range. The radius therefore never depends on this simulator's car model. Example: a 50 km/h hairpin gets r ≈ 9.8 m, within the encyclopedia's "6–15 m" for true hairpins.
- **Builders:** `turn(speed, angle)` makes an arc of `angle` degrees. `hairpin`, `chicane(*speeds, angle)`, `esses` and `spiral(entry, exit, angle)` build the other types. A spiral's length follows from its turn angle and mean curvature.
- **Straights:** `build_track` scales every straight by one factor, `straight_scale`, so the lap equals `official_length`. Rises are given in metres and kept when a straight is scaled, and each layout's rises sum to zero. The scale (0.89–1.52) shows how far the estimated straights were off.

28 circuits:

| Group | Circuits |
|---|---|
| Europe | Monza, Spa, Silverstone, Monaco, Barcelona (4.675 km layout), Zandvoort, Red Bull Ring, Hungaroring, Imola, Madrid, Istanbul |
| Americas | COTA, Miami, Mexico, Interlagos, Las Vegas, Montreal |
| Asia, Pacific, Middle East | Bahrain, Jeddah, Suzuka, Shanghai, Singapore (2023–24 layout), Lusail, Yas Marina, Baku, Albert Park, Sepang, Buddh |

`MonzaV0` is the V0 layout, unchanged. The V0–V5 regression tests and the README's V2–V5 examples use it, so they keep guarding the simulator rather than the new geometry.

### 4.1 How good are the layouts?

They are not validated: real corner geometry was not available. Two checks are made:

- **Monza calibration (V6 rerun on the new layout):** the calibrated model matches 2024 qualifying (bias 0 by construction, MAE 0.49 s) and held-out 2025 qualifying (MAE 0.56 s; V6: 0.52 s). It still names the wrong fastest team in 2025.
- **All circuits against their race lap records:** the calibrated model is a median 5.9 % faster than the record, with a range from −17.6 % to +2.3 % (table in the validation report).
  - Race lap records are race laps by other cars in other years, so they are usually slower than the qualifying pace the grip was fitted to. Some negative error is expected.
  - **Zandvoort, −17.6 %:** banking is counted twice. The radius comes from the speed the banked corner already allows, and the model then adds the banking again.
  - **Mexico, −14.6 %:** altitude (2,285 m, thinner air) is not modelled.
  - **Jeddah and Suzuka, about −14 %:** high-speed corner estimates (the encyclopedia's and the author's) are probably too fast.

## 5. Calibration (`validation/`)

There is no code change to the V6 method.

- **Grip:** `python3 -m validation.calibrate` refits grip on the new Monza: **2.4811** (V6: 2.9358). The new layout's slow corners are faster, so less "effective grip" is needed.
- **Pit loss:** 25.62 s, unchanged.
- **Report:** `validation.evaluate` adds a section comparing every circuit with its lap record. `flying_laps` gains an optional `track` argument for it.

The calibrated value is still an effective parameter, not a tyre property.

## 6. RL environment (`rl/env.py`)

Changes to `StrategyEnv`:

| Option | V7/V8 | V9 |
|---|---|---|
| `track` | Monza only | Any name in `tracks.CIRCUITS` (default `"Monza"`). One track instance per environment, so lap profiles can be cached across races. |
| `laps` | 53 | `None`: the circuit's Grand Prix distance |
| grip | simulator default 1.8 | `calibration="calibrated"`: every compound's grip × 2.4811 / 1.8, as in `validation.model`. `"baseline"` gives V7. |
| `pit_loss` | fixed 22 s | `None`: hidden, random per race. A number fixes it. |
| `neutralisation_chance`, `rain_chance` | 0.5, 0.25 | `None`: the circuit's values |
| fuel | 1.9 kg/lap, exactly enough fuel | Hidden burn rate. The car is fuelled for the highest possible rate. |
| tyre wear | fixed per compound | Hidden multiplier |

**Hidden conditions**, drawn by `_draw_scenario` after V7's event draws so a seed's event sequence keeps its draw order:

| Condition | Draw |
|---|---|
| Pit loss | circuit value + U(−2.5, 2.5) s. Monza: 25.62 (measured). Others: 22.5 (the encyclopedia's 20–25 s). Always drawn, so fixing it leaves the other draws of a seed unchanged. |
| Fuel burn | `FUEL_PER_KM` (0.32 kg/km, new in `race.py`) × lap length × U(0.92, 1.08). Start fuel = laps × nominal × 1.08, which must fit the 110 kg tank (`ValueError` otherwise). |
| Tyre wear | circuit `tyre_wear` × U(0.75, 1.25), applied to every compound's `wear_per_lap` |
| VSC / Safety Car | as V7, with the circuit's chance |
| Rain | as V7, with the circuit's chance |

**What the agent sees:**
- The observation is unchanged (19 floats). The agent learns these conditions only through their effects: the fuel gauge falls faster or slower, tyre wear rises faster or slower, flags and wetness appear.
- `info["scenario"]["hidden"]` records the values for analysis. `rl.evaluate.run_episode` and the research runner give a policy only the observation and mask.

**Settings per circuit** (model assumptions grounded in the encyclopedia's categories):

| Setting | Default | Higher or lower at |
|---|---|---|
| Neutralisation chance | 0.5 | 0.7 on street circuits (Monaco, Baku, Jeddah, Las Vegas, Madrid); 0.9 at Singapore |
| Rain chance | 0.25 | 0.4 at wet-prone circuits (Spa, Silverstone, Interlagos, Montreal, Suzuka, Sepang); 0.05 at desert venues |
| Tyre wear | 1.0 | 1.2 at the seven tyre-demanding circuits; 0.8 at Albert Park |

`main.py` takes an optional track name and scales fuel per lap with the circuit length. It still uses the simulator defaults, not the calibration.

## 7. Research and experiments (`research/`, `rl/experiment.py`)

**Config schema:**
- `env` is now `{"team", "track"}`. Pit loss is no longer configurable there, because it is hidden.
- The sensitivity analysis may still fix it. The committed config uses `{"pit_loss": 22.0}`: the old placeholder, to show what the correction changed.
- The V8 question, designs, seeds, CEM budget and decision rule are unchanged.

Both experiments were re-run on the final V9 code. Results are in §8.

## 8. Results

All runs are on the final V9 code. The V8 results file records code digest `88b54f1a…`, which a test checks against the committed code. Results describe **this simulator** at Monza with the V9 settings, not real F1.

### 8.1 V7 experiment (`python3 -m rl.experiment`, 20 held-out races; [report](../../../rl/reports/experiment_report.md))

| Policy | vs hand-set rule-based: mean ± std (s per race) | Better / worse | V7 (old settings) |
|---|---|---|---|
| fixed one-stop | +2.8 ± 12.2 | 8 / 12 | +4.2 ± 12.7 |
| stay out | +27.2 ± 12.8 | 1 / 19 | +40.7 |
| random (10 % pit) | +149.5 ± 88.2 | 0 / 20 | +164 |
| CEM-tuned | +0.0 | identical | +0.2 ± 5.4 |

The cross-entropy search found **no candidate better than the hand-set thresholds** on its 3 training races, so the "tuned" policy is the hand-set rule.

Race times are about 4,370 s, not V7's 5,190 s, because of the calibrated grip and the new Monza. The real 2024 race took 4,481 s.

### 8.2 V8 experiment re-run (`python3 -m research.scenario_coverage`; [report](../../../research/results/scenario_coverage.md))

Same question, designs, seeds, CEM budget and decision rule as V8. 0 failed episodes, 38 min on 7 processes.

**Training gain** of the tuned thresholds over the hand-set ones, on that run's own 6 races (s per race):

| Design | Run 0 | Run 1 | Run 2 |
|---|---|---|---|
| random | 0.00 | 3.38 | 0.22 |
| stratified | 2.84 | 3.39 | 0.06 |

**Main evaluation:** hidden random pit loss, 40 held-out races (14 quiet, 18 neutralised, 8 wet). Paired difference against the hand-set rule:

| Policy | Mean ± std (s) | 95 % CI | Better / worse / tie |
|---|---|---|---|
| fixed one-stop | −0.25 ± 7.98 | [−2.67, +2.26] | 16 / 20 / 4 |
| tuned random run 0 | 0.00 | [0, 0] | identical (hand-set returned) |
| tuned random run 1 | +0.44 ± 1.71 | [−0.02, +0.96] | 7 / 19 / 14 |
| tuned random run 2 | +2.36 ± 7.88 | [+0.33, +5.01] | 18 / 12 / 10 |
| tuned stratified run 0 | +0.09 ± 3.64 | [−1.07, +1.09] | 9 / 21 / 10 |
| tuned stratified run 1 | +0.77 ± 4.74 | [−0.71, +2.09] | 5 / 25 / 10 |
| tuned stratified run 2 | +0.57 ± 4.18 | [−0.15, +1.96] | 12 / 7 / 21 |

**Decision rule:** random has 0 of 3 runs with a CI below 0, so it does **not** help. Stratified has 0 of 3, so it does **not** help. This is the same verdict as V8.

**Sensitivity:** the same policies and races with the pit loss fixed at V7/V8's old 22 s.
- Verdicts are unchanged.
- The fixed one-stop is **+2.84 s**, CI [+0.24, +5.84]. Almost all of that comes from wet races (+14.9 s, n = 8).
- In the main evaluation its wet-race difference is −0.4 s.

### 8.3 Conclusions

| Conclusion | Status |
|---|---|
| Neither training design makes threshold tuning beat the hand-set rule (V8's question) | **Supported again**, with the corrected settings |
| Tuning overfits its training races (e.g. 3.4 s per race gained on training, +0.4 to +0.8 s per race on held-out) | **Supported** |
| The hand-set rule beats a fixed one-stop | **Not supported** at the measured, randomised pit loss (CI [−2.67, +2.26]). Supported only at the old 22 s. |
| The rule's advantage came from reacting to rain with extra stops, which pays only when stops are cheap | **Consistent with** the wet-stratum differences (+14.9 s at 22 s, −0.4 s at ~25.6 s). Only 8 wet races; the mechanism was not traced race by race. |
| Anything about real F1 | **Not claimed** |

**What the correction changed:**
- **The research verdict is the same.**
- **The headline "the rule beats a fixed one-stop" from V7/V8 was an artefact of the 22 s placeholder pit loss.** V8's sensitivity analysis already hinted at this.
- **The wet-race comparison rests on 8 races.**

## 9. Licensing

- **Code:** Apache-2.0 (`LICENSE`), unchanged and open source.
- **Timing data:** `data/reference/raw/*.json` (Jolpica-F1 / Ergast) is CC BY-NC-SA 4.0. A repository may contain material under different licences if each part is clearly marked. V9 marks it:
  - `data/reference/LICENSE.md` explains the licence and what it means here;
  - a root `NOTICE` lists all third-party material;
  - the README has a "Licence and credits" section.
- **Files that reproduce data values:** the validation report and the fitted numbers in `calibrated.json` are declared to be under the same licence.
- **Non-commercial use:** learning, research and a portfolio are fine. Commercial use needs permission; Jolpica-F1's Terms of Use name the contact.
- **Other ways out, not taken:**
  - (a) Do not commit the data; download it with `validation/fetch_reference.py` and make the V6 tests skip without it. The repository would then be Apache-2.0 only.
  - (b) Ask Jolpica-F1 for permission.
- **Credits:**
  - Jolpica-F1 and its contributors, and the Ergast API they continue: data.
  - LordZeusIsBack, F1-Encyclopedia: circuit information.
  - Wikipedia: gap-filling facts.

  No text was copied from either written source, only facts and estimates, each attributed.
- **F1-Encyclopedia licence:** the repository has no licence file. Its owner can add one, for example CC BY 4.0, if others are to reuse it.

This is not legal advice.

## 10. Limitations

- **Circuits:**
  - approximate layouts;
  - no altitude, track width, crests or kerbs;
  - banking is counted twice where the source speed already includes it;
  - one effective grip, fitted at Monza, for all circuits.
- **Hidden-condition ranges:** assumptions, not measurements, except Monza's pit loss.
- **Pit loss:** the same generic value at every circuit except Monza.
- **Fuel:** burn varies per race but not with driving.
- **Tyres:** wear varies per race, not per stint or with temperature.
- **The agent still races alone** in the experiments.
- **Results** describe this simulator, not real F1.
