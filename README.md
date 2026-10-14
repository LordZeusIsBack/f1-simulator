# F1 Strategist

A Python simulation of Formula 1 cars racing around a track. It grows one small, documented version at a time, towards a platform for race-strategy and reinforcement-learning experiments.

The physics, car parameters, tyre and fuel values, traffic rules, weather model and race-control rules are **simplified**, and most of their numbers are assumptions. Since V9 the simulator has 28 real circuits, built approximately from public estimates. V6/V9 measure how far the model is from real F1 timing data. At Monza the calibrated model is within about 0.6 s of real qualifying laps; see [Validation](#validation-v6-recalibrated-in-v9).

## Current version: V9 — real circuits, richer track geometry, randomised race conditions

- **V0:** a simplified physics model computes a flying-lap speed profile and lap time for one car.
- **V1:** several cars start from a grid and race a set number of laps, with positions, laps and gaps.
- **V2:** tyres wear and lose grip, and fuel burns off and makes the car lighter. Cars pit to change tyres and/or refuel, following a fixed strategy.
- **V3:** cars interact:
  - dirty air costs pace in corners;
  - DRS helps on long straights;
  - a car can only pass on a straight with enough speed advantage, otherwise it is held up behind.

  Drivers have `pace` and `racecraft`. Every pass and refused attempt is logged.
- **V4:** a scripted weather timeline sets air temperature and rain. Track wetness rises and falls smoothly, and wetness costs slicks far more grip than intermediates or wets, so the best tyre changes. Strategies can react by pitting for better tyres. Rain changes and changes of the best tyre are logged.
- **V5:** race control:
  - a local yellow, a Virtual Safety Car and a Safety Car, each with defined effects and a defined end;
  - scripted incidents that call flags and/or retire cars;
  - time and drive-through penalties, and a two-dry-compound rule;
  - a race-control event log;
  - a classification by race time including penalties, with retired cars at the bottom.
- **V6:** no new simulator features. V6 adds:
  - a parameter audit;
  - a small real dataset (Monza 2024 and 2025, Jolpica-F1 / Ergast);
  - a repeatable validation workflow;
  - a 2-parameter calibration on 2024, evaluated on held-out 2025, with the baseline kept;
  - a generated report.
- **V7:** an RL environment, `rl.env.StrategyEnv`, with Gymnasium-style `reset()` and `step()`. The agent makes the pit calls for one car at Monza while random, seeded VSC/SC and rain scenarios play out. V7 also adds four baseline policies, a seeded evaluation harness, and a small policy-search experiment.
- **V8:** one controlled research experiment: does the training-race mix decide whether tuning beats the hand-set rule? It has a configuration file, parallel failure-tolerant runs, bootstrap statistics, and stored results tied to the code. Result: **negative**, neither training design beat the hand-set rule.
- **V9 (new):** requested after the roadmap. V9 adds:
  - 28 approximate real circuits (Sepang, Baku, Singapore, Buddh, COTA, Imola, Monaco, Spa and more) built from [F1-Encyclopedia](https://github.com/LordZeusIsBack/F1-Encyclopedia);
  - new segment types: hairpins, chicanes, esses, spirals (decreasing or increasing radius) and banked corners;
  - recalibration on the new Monza;
  - an RL environment that uses the calibrated grip and any circuit, with hidden, random pit loss, fuel burn and tyre wear in every race;
  - re-runs of the V7 and V8 experiments;
  - licence notices and credits.

  See [Tracks](#tracks-v9) and [Licence and credits](#licence-and-credits).

## Phase 2: AI driver (in progress)

Phase 1 (V0–V9) built the race world and a pit-strategy agent. Phase 2 adds an AI driver in six milestones, ending with a driver and a strategist that decide at different levels. Phase 2 work is on `ai-agent-branch`.

| Milestone | Status | Docs |
|---|---|---|
| P2-V1 Driver skills and profiles | **done** | [Implementation](docs/phase2/p2-v1/IMPLEMENTATION.md) · [Code flow](docs/phase2/p2-v1/CODE_FLOW.md) · [Changelog](docs/phase2/p2-v1/CHANGELOG.md) |
| P2-V2 Driver decision interfaces and rule-based baseline policies | not started | |
| P2-V3 On-track driving control | not started | |
| P2-V4 Trainable AI driver | not started | |
| P2-V5 Driver-versus-driver competition | not started | |
| P2-V6 Hierarchical race intelligence | not started | |

**P2-V1:** `Driver` gains five skills, each 0–1:
- `attack` and `defence` split the V3 `racecraft` term of the overtaking rule. The speed advantage a pass needs is now 2.0 − 1.0 × (attacker's `attack` − defender's `defence`) m/s. Both default to the driver's `racecraft`, so existing profiles and results are unchanged.
- `tyre_management`, `consistency` and `wet_weather` are **profile only**: stored and validated, with no effect on a race yet. Their planned mechanisms are in the [implementation notes](docs/phase2/p2-v1/IMPLEMENTATION.md#4-the-profile-attribute-by-attribute).

```python
Driver("Rookie", racecraft=0.1, defence=0.9)  # attacks like racecraft 0.1, defends like 0.9
```

Skill values are model inputs for fictional drivers, not ratings of real people.

## Requirements and setup

- Python 3.12 or newer. There are no third-party dependencies.
- [uv](https://docs.astral.sh/uv/) is optional; the repository includes a `uv.lock`.

```bash
git clone https://github.com/LordZeusIsBack/f1-simulator.git
cd f1-simulator
git checkout ai-agent-branch
```

## Running

```bash
python3 main.py            # lap table, then a Monza Grand Prix (53 laps) with traffic
python3 main.py 10         # a 10-lap race (at least 2 laps, so the one-stop plan fits)
python3 main.py 20 Baku    # 20 laps of another circuit; an unknown name lists them all
uv run main.py             # the same through uv
```

`main.py` uses the simulator's own defaults (grip 1.8, pit loss 22 s), not the calibrated values. Fuel per lap scales with the circuit's length.

Each team runs one car on **"no stop (M)"** and one on **"1 stop (M-H)"**, so the two plans meet on identical cars. The program prints:

- the standings after lap 1;
- the final classification, with a strategy column;
- the pit-stop log: lap, time, old tyres and their wear, new tyres, fuel added, stop duration;
- the overtake log: each pass with the speed advantage, the margin needed and DRS, plus how often cars were held up.

## Tracks (V9)

`tracks.CIRCUITS` maps a name to a circuit class. There are 28:

- **Europe:** Monza, Spa, Silverstone, Monaco, Barcelona, Zandvoort, RedBullRing, Hungaroring, Imola, Madrid, Istanbul;
- **Americas:** COTA, Miami, Mexico, Interlagos, LasVegas, Montreal;
- **Asia, Pacific and Middle East:** Bahrain, Jeddah, Suzuka, Shanghai, Singapore, Lusail, YasMarina, Baku, AlbertPark, Sepang, Buddh.

```python
from tracks import CIRCUITS
track = CIRCUITS["Sepang"]()
track.length, track.laps, track.lap_record     # 5543.0 m, 56, 94.08 s
```

Segment types (`abstract_classes.py`). Each one is cut into 1 m points for the lap model:

| Type | Built from | Lap-model effect |
|---|---|---|
| `Straight` | length, gradient | No corner limit |
| `Corner` | length, radius, gradient, `banking` | Constant radius |
| `Hairpin` | radius, angle (default 180°) | Length = radius × angle |
| `Spiral` | length, entry radius, exit radius | Curvature changes linearly along it (decreasing- or increasing-radius corners such as Parabolica or Shanghai T1) |
| `Chicane`, `Esses` | two or more parts | Each part is driven in turn; one segment for race control and traffic |
| any segment | `banking` in degrees | Positive banking raises the cornering limit (Zandvoort T3/T14, Madrid's La Monumental); negative = off-camber |

How a circuit is built (details in [V9 IMPLEMENTATION.md](docs/versions/v9/IMPLEMENTATION.md)):

1. **Corner radius:** from the corner's estimated minimum speed and the encyclopedia's lateral-g table for that speed.
2. **Straights:** scaled so the lap equals the official length.
3. **Elevation:** given in metres, and sums to zero over a lap.

These are **approximations**, not surveyed geometry. The corner speeds are estimates, mostly from the encyclopedia and otherwise by the V9 author. As a sanity check, the calibrated model's laps are compared with each circuit's race lap record in the [validation report](validation/reports/validation_report.md). The median is −5.9 %, with a range from −17.6 % (Zandvoort, where banking is counted twice) to +2.3 %.

`tracks.MonzaV0` is the original layout, kept so the V0–V5 regression tests still guard the simulator itself.

## Configuration (V2)

| Where | Option | Default | Meaning |
|---|---|---|---|
| `Race(...)` | `pit_loss` | 22.0 s | Time a stop costs, before refuelling |
| `Race(...)` | `fuel_per_lap` | 1.9 kg | Fuel burned per lap; 0 turns fuel effects off |
| `Race(...)` | `compounds` | `tyres.COMPOUNDS` | `{TyreCompound: Compound(grip, wear_per_lap)}` |
| `RaceCar(...)` | `strategy` | `None` | A `Strategy`; `None` means no stop on mediums with just enough fuel |
| `strategy.py` | `Strategy(compound, fuel, stops, name)` | — | Start tyres, start fuel (kg), stops |
| `strategy.py` | `PitStop(lap, compound=None, fuel=0.0)` | — | Stop as `lap` is completed; fit a new `compound` and/or add `fuel` kg |
| `tyres.py` | `COMPOUNDS`, `WORN_GRIP_LOSS` | soft 1.83 / 0.05, medium 1.80 / 0.03, hard 1.775 / 0.02; 0.06 | New-tyre grip, wear per lap, grip lost at full wear |
| `race.py` | `FUEL_CAPACITY`, `REFUEL_RATE` | 110 kg, 10 kg/s | Tank size, refuelling speed |

Plans that are impossible are rejected with `ValueError` before the race starts. Examples:

- a stop on lap 0, or on the final lap;
- two stops in one lap;
- a stop that changes nothing;
- a compound not in the race's `compounds` table (since V4 the default table includes intermediates and wets);
- negative fuel;
- an overfilled tank;
- running out of fuel.

### Traffic and drivers (V3)

| Where | Option | Default | Meaning |
|---|---|---|---|
| `Race(...)` | `traffic` | `TrafficRules()` | Traffic rules; `None` turns interactions off (V2 behaviour) |
| `RaceCar(...)` | `driver` | `Driver()` | `Driver(name, pace=1.0, racecraft=0.5)`; both attributes 0–1 |
| `TrafficRules` | `min_gap` | 5 m | Closest a car follows unless it is passing |
| `TrafficRules` | `dirty_air_interval`, `dirty_air_loss` | 1.0 s, 0.02 | Closer than this costs 2 % pace in corners |
| `TrafficRules` | `drs_interval`, `drs_from_lap`, `drs_min_straight`, `drs_gain` | 1.0 s, 3, 500 m, 0.035 | DRS for the next lap if under 1.0 s at the line, from lap 3, on straights of 500 m or more, 3.5 % less time there |
| `TrafficRules` | `overtake_margin`, `racecraft_effect` | 2.0 m/s, 1.0 m/s | Speed advantage needed on a straight: 2.0 − 1.0 × (attacker − defender racecraft) |
| `drivers.py` | `PACE_SPREAD` | 0.01 | A pace-0 driver is 1 % slower |

With traffic, results depend on the step size `dt`, because interactions are decided once per step. `main.py` uses 0.1 s.

### Weather (V4)

| Where | Option | Default | Meaning |
|---|---|---|---|
| `Race(...)` | `weather` | `None` | A `Weather`; `None` means always dry (V3 behaviour). Use a new `Weather` for each race. |
| `weather.py` | `Weather(timeline, wetness=0.0)` | — | Timeline of `WeatherPoint`s plus the starting wetness (0 dry to 1 fully wet) |
| `weather.py` | `WeatherPoint(time, air_temp, rain=0.0)` | — | Keyframe: s, °C (−10 to 50), mm/h (0 to 50). Linear between keyframes, held before and after. |
| `weather.py` | `WETTING_RATE`, `DRYING_RATE`, `DRYING_MIN_TEMP`, `SUN_HEATING` | 0.001 /s per mm/h, 3·10⁻⁵ /s per °C, 0 °C, 15 °C | dW/dt = k_wet(1 − W) − k_dry W; track temperature = air + 15 × (1 − W) |
| `tyres.py` | `Compound(grip, wear_per_lap, wet_loss)` | slicks 0.65, inter 0.32, wet 0.15 | Fraction of grip lost on a fully wet track |
| `tyres.py` | `COMPOUNDS` / `DRY_COMPOUNDS` | all five / slicks only | Compound tables (`DRY_COMPOUNDS` is V2's set) |
| `strategy.py` | `Strategy(..., react_to_weather=False)`, `WEATHER_MARGIN` | off, 0.05 | Pit for `best_compound` when it has more than 5 % more grip than the current compound |
| `race.py` | `WETNESS_STEP` | 0.05 | Lap profiles are rebuilt mid-lap whenever wetness has moved this much |

To reproduce earlier versions:

- **V1:** `fuel_per_lap=0.0`, `compounds={TyreCompound.MEDIUM: Compound(TYRE_GRIP, 0.0)}` and `traffic=None`.
- **V2:** `traffic=None`.
- **V3:** `weather=None`, the default.
- **V4:** `race_control=None`, the default.

### Race control (V5)

| Where | Option | Default | Meaning |
|---|---|---|---|
| `Race(...)` | `race_control` | `None` | A `RaceControl`; `None` means always green, no incidents or penalties (V4). Use a new one for each race. |
| `race_control.py` | `RaceControl(incidents, penalties, rules)` | — | Scripted incidents and penalties plus the rules |
| `race_control.py` | `Incident(time, flag=None, duration=0, retire=None, segment=None, reason="")` | — | At `time` s: retire car `retire` and/or call `Flag.YELLOW` (in `segment`, or where the car stopped), `VSC` or `SAFETY_CAR` for `duration` s |
| `race_control.py` | `Penalty(time, car, kind="time", seconds=5.0, reason="")` | — | `"time"`: + `seconds` to the race time. `"drive-through"`: a 20 s pit-lane pass at the next green or yellow crossing (+20 s if the car finishes first). |
| `RaceControlRules` | `yellow_slowdown` | 0.10 | 10 % slower inside the yellow segment, no passing there |
| `RaceControlRules` | `vsc_factor` | 1.40 | Every car 40 % slower, no passing |
| `RaceControlRules` | `sc_factor`, `sc_catch_up_factor`, `sc_gap` | 1.60, 1.30, 10 m | SC queue: the leader at 1.6, the others close up at 1.3 to 10 m apart, no passing |
| `RaceControlRules` | `drive_through_loss` | 20 s | Cost of a drive-through |
| `RaceControlRules` | `two_compound_penalty` | 30 s | For a finisher with no wet tyres and only one dry compound; 0 = off |
| `RaceControlRules` | `drs_max_wetness` | 0.3 | DRS only under green and on a track no wetter than this |

Flags only escalate (GREEN → YELLOW → VSC → SAFETY_CAR). Each one ends by itself:

- YELLOW and VSC end after their duration;
- the SC ends after its duration, at the moment the leader crosses the line.

`race.standings()` ranks finished cars by `race.total_time(car)` (finish time plus penalties), then running cars, then retired cars.

## Strategy comparison example

The examples below use `MonzaV0`, the layout of their version, so their printed numbers stay valid. The same car (McLaren) runs alone over 53 laps of Monza with default settings, once per plan. The run is deterministic and takes about 9 s:

```bash
python3 - <<'EOF'
from abstract_classes import TyreCompound as T
from cars import CARS
from race import FUEL_PER_LAP, Race, RaceCar
from strategy import PitStop, Strategy
from tracks import MonzaV0

laps, fuel = 53, 53 * FUEL_PER_LAP
plans = [
    Strategy(T.HARD, fuel, name="no stop (H)"),
    Strategy(T.MEDIUM, fuel, name="no stop (M)"),
    Strategy(T.MEDIUM, fuel, (PitStop(26, T.HARD),), name="1 stop (M-H)"),
    Strategy(T.SOFT, fuel, (PitStop(17, T.MEDIUM), PitStop(35, T.SOFT)), name="2 stops (S-M-S)"),
    Strategy(T.MEDIUM, 26 * FUEL_PER_LAP, (PitStop(26, T.HARD, 27 * FUEL_PER_LAP),), name="1 stop + refuel"),
]
for plan in plans:
    car = RaceCar(1, "McLaren", CARS["McLaren"], plan)
    race = Race(MonzaV0(), laps, [car])
    race.run()
    print(f"{plan.name:<16} {car.finish_time:9.3f} s  stops {len(race.pit_events)}")
EOF
```

Expected output:

```
no stop (H)       5124.340 s  stops 0
no stop (M)       5116.691 s  stops 0
1 stop (M-H)      5110.338 s  stops 1
2 stops (S-M-S)   5104.174 s  stops 2
1 stop + refuel   5087.915 s  stops 1
```

The ranking follows from the placeholder parameters, not from real tyre data. See [V2 IMPLEMENTATION.md §10](docs/versions/v2/IMPLEMENTATION.md#10-strategy-comparison).

## Traffic and overtaking example

Three cars race 6 laps of Monza. A slow Mercedes with a strong defender leads two identical McLarens: a low-racecraft "Rookie" and a high-racecraft "Veteran". The same race is run with traffic and without. It takes about 1.3 s:

```bash
python3 - <<'EOF'
from cars import CARS
from drivers import Driver
from race import Race, RaceCar
from tracks import MonzaV0

for traffic in ("on", "off"):
    grid = [
        RaceCar(1, "Mercedes", CARS["Mercedes"], driver=Driver("Defender", racecraft=0.9)),
        RaceCar(2, "McLaren", CARS["McLaren"], driver=Driver("Rookie", racecraft=0.1)),
        RaceCar(3, "McLaren", CARS["McLaren"], driver=Driver("Veteran", racecraft=0.9)),
    ]
    race = Race(MonzaV0(), 6, grid, **({} if traffic == "on" else {"traffic": None}))
    race.run(0.1)
    print(f"traffic {traffic}:", ", ".join(f"#{c.number} {c.driver.name} {c.finish_time:.3f} s" for c in race.standings()))
    for e in race.overtakes:
        if e.outcome != "held up":
            print(f"  lap {e.lap} {e.time:6.1f} s  #{e.attacker} on #{e.defender}: {e.outcome:<7}"
                  f" advantage {e.advantage:+.2f} m/s, needed {e.required:.2f}{', DRS' if e.drs else ''}")
    if race.overtakes:
        print(f"  held up {sum(e.outcome == 'held up' for e in race.overtakes)} times")
EOF
```

Expected output:

```
traffic on: #3 Veteran 567.052 s, #2 Rookie 568.365 s, #1 Defender 574.202 s
  lap 2  104.6 s  #2 on #1: aborted advantage +4.31 m/s, needed 2.80
  lap 2  119.7 s  #2 on #1: aborted advantage +3.46 m/s, needed 2.80
  lap 3  192.3 s  #2 on #1: passed  advantage +6.56 m/s, needed 2.80, DRS
  lap 3  192.8 s  #3 on #1: passed  advantage +4.70 m/s, needed 2.00, DRS
  lap 5  400.5 s  #3 on #2: aborted advantage +1.31 m/s, needed 1.20, DRS
  lap 6  486.6 s  #3 on #2: passed  advantage +3.55 m/s, needed 1.20, DRS
  held up 14 times
traffic off: #2 Rookie 565.960 s, #3 Veteran 566.098 s, #1 Defender 573.457 s
```

What it shows:

- **The Rookie is held up.** Against the strong defender it needs 2.8 m/s, so it stays stuck behind until DRS is allowed from lap 3.
- **The Veteran waits for DRS too.** It needs only 2.0 m/s to pass the Mercedes, but it is stuck behind the Rookie's identical car until a DRS pass on the last lap.
- **Without traffic** the McLarens simply drive through, the Rookie wins on grid position, and all three finish 0.7–2.4 s sooner.

## Weather example

A dry race turns wet, then dries again. It runs 20 laps of Monza with two identical McLarens on mediums: one stays out, the other reacts to the weather. It takes about 4 s:

```bash
python3 - <<'EOF'
from abstract_classes import TyreCompound as T
from cars import CARS
from race import FUEL_PER_LAP, Race, RaceCar
from strategy import Strategy
from tracks import MonzaV0
from weather import Weather, WeatherPoint

laps = 20
timeline = [
    WeatherPoint(0, 24.0),          # dry, 24 °C air
    WeatherPoint(500, 24.0),
    WeatherPoint(560, 21.0, 6.0),   # a shower builds to 6 mm/h over a minute
    WeatherPoint(1100, 19.0, 6.0),
    WeatherPoint(1160, 19.0, 0.0),  # rain stops; the track starts drying
    WeatherPoint(2000, 22.0),
]
grid = [
    RaceCar(1, "McLaren", CARS["McLaren"], Strategy(T.MEDIUM, laps * FUEL_PER_LAP, name="stays out")),
    RaceCar(2, "McLaren", CARS["McLaren"], Strategy(T.MEDIUM, laps * FUEL_PER_LAP, name="reacts", react_to_weather=True)),
]
race = Race(MonzaV0(), laps, grid, weather=Weather(timeline))
race.run(0.1)
for e in race.weather_events:
    c = e.conditions
    print(f"{e.time:6.1f} s  {e.kind:<11}  wetness {c.wetness:.2f}  track {c.track_temp:4.1f} °C  best: {e.best.value}")
for stop in race.pit_events:
    print(f"#{stop.number} pits after lap {stop.lap}: {stop.tyres_before.compound.value} -> {stop.tyres_after.compound.value}")
for car in race.standings():
    print(f"#{car.number} {car.strategy.name:<9} {car.finish_time:8.3f} s, finished on {car.tyres.compound.value}")
EOF
```

Expected output:

```
 500.0 s  rain starts  wetness 0.00  track 39.0 °C  best: soft
 621.0 s  best tyres   wetness 0.40  track 29.7 °C  best: intermediate
 748.6 s  best tyres   wetness 0.68  track 25.1 °C  best: wet
1160.0 s  rain stops   wetness 0.87  track 21.0 °C  best: wet
1513.0 s  best tyres   wetness 0.68  track 25.0 °C  best: intermediate
2129.9 s  best tyres   wetness 0.40  track 30.9 °C  best: soft
#2 pits after lap 7: medium -> intermediate
#2 pits after lap 11: intermediate -> wet
#2 pits after lap 19: wet -> intermediate
#2 reacts    2172.144 s, finished on intermediate
#1 stays out 2235.413 s, finished on medium
```

What it shows:

- **The track wets and dries gradually.** Wetness rises during the shower and falls after it, and the best tyre follows it: soft → intermediate (W ≥ 0.40) → wet (W ≥ 0.68), then back.
- **The reacting car wins by 63 s.** It pits for inters, then wets. Its last stop, after lap 19 of 20, is wasted, because the simple rule ignores how many laps remain.
- **The car that stays out suffers in the wet.** On mediums it laps up to about 133 s, against about 110 s for the car on wets.

## Race control example

This race runs 12 laps of Monza with 6 cars. During it:

- one car retires and brings out a yellow;
- a Safety Car comes out;
- one car gets a time penalty and another a drive-through;
- the two no-stop cars break the two-compound rule.

It takes about 3 s:

```bash
python3 - <<'EOF'
from abstract_classes import TyreCompound as T
from cars import CARS
from race import FUEL_PER_LAP, Race, RaceCar
from race_control import Flag, Incident, Penalty, RaceControl
from strategy import PitStop, Strategy
from tracks import MonzaV0

laps = 12
one_stop = Strategy(T.MEDIUM, laps * FUEL_PER_LAP, (PitStop(6, T.HARD),), name="1 stop")
no_stop = Strategy(T.MEDIUM, laps * FUEL_PER_LAP, name="no stop")
entries = [("McLaren", one_stop), ("Red Bull", one_stop), ("Ferrari", one_stop),
           ("Mercedes", no_stop), ("McLaren", one_stop), ("Red Bull", no_stop)]
grid = [RaceCar(n, team, CARS[team], plan) for n, (team, plan) in enumerate(entries, start=1)]
control = RaceControl(
    incidents=[
        Incident(300, Flag.YELLOW, 40, retire=3, reason="Ferrari #3 stops"),
        Incident(500, Flag.SAFETY_CAR, 120, segment=0, reason="debris on the main straight"),
    ],
    penalties=[
        Penalty(150, 2, "time", 5, reason="track limits"),
        Penalty(200, 5, "drive-through", reason="unsafe release"),
    ],
)
race = Race(MonzaV0(), laps, grid, race_control=control)
race.run(0.1)
for e in control.events:
    print(f"{e.time:7.1f} s  {e.kind:<16} {e.flag.name:<10} {e.detail}")
for position, car in enumerate(race.standings(), start=1):
    result = "DNF" if car.retired_at is not None else f"{race.total_time(car):8.3f} s"
    penalty = f"  (incl. +{car.penalty_time:g} s penalty)" if car.penalty_time else ""
    print(f"{position}. #{car.number} {car.team:<8} {car.strategy.name:<7} {result}{penalty}")
EOF
```

Expected output:

```
  150.1 s  penalty          GREEN      +5 s for #2: track limits
  200.1 s  penalty          GREEN      drive-through for #5: unsafe release
  286.1 s  penalty served   GREEN      #5 drive-through after lap 3
  300.1 s  retirement       GREEN      #3 out on lap 4: Ferrari #3 stops
  300.1 s  flag             YELLOW     GREEN -> YELLOW: Ferrari #3 stops
  340.1 s  flag             GREEN      YELLOW -> GREEN: YELLOW period over
  500.0 s  flag             SAFETY_CAR GREEN -> SAFETY_CAR: debris on the main straight
  760.6 s  flag             GREEN      SAFETY_CAR -> GREEN: safety car in; restart at the line
 1238.1 s  penalty          GREEN      +30 s for #6: used only one dry compound
 1240.8 s  penalty          GREEN      +30 s for #4: used only one dry compound
1. #1 McLaren  1 stop  1233.857 s
2. #5 McLaren  1 stop  1238.207 s
3. #2 Red Bull 1 stop  1242.489 s  (incl. +5 s penalty)
4. #6 Red Bull no stop 1268.120 s  (incl. +30 s penalty)
5. #4 Mercedes no stop 1270.767 s  (incl. +30 s penalty)
6. #3 Ferrari  1 stop  DNF
```

What happens:

- **The SC bunches the field and lasts 260 s.** It ends only when the leader crosses the line after its 120 s minimum.
- **Cheap stops reshuffle the order.** The one-stoppers pit under the SC, so the no-stoppers lead the restart, but they are passed within 14 s.
- **The 5 s penalty costs #2 a place.** #2 crosses the line 0.7 s ahead of #5 but is classified behind it.
- **The retired #3 is classified last.**

## Validation (V6, recalibrated in V9)

The comparison uses the real public timing data from the 2024 and 2025 Italian GPs in `data/reference/raw/`.

- **Source:** Jolpica-F1 API (Ergast-compatible), accessed 2026-10-12.
- **Licence:** **CC BY-NC-SA 4.0**, non-commercial use only. See [data/reference/README.md](data/reference/README.md).

Everything below runs offline from the committed files:

```bash
python3 -m validation.calibrate    # fit tyre_grip and pit_loss on 2024 only -> validation/config/calibrated.json
python3 -m validation.evaluate     # baseline and calibrated vs 2024 and 2025, plus every circuit vs its lap record
                                   # -> validation/reports/validation_report.md (about 16 s)
python3 test_validation.py         # data checks, metrics, reproducibility, "report is up to date" (about 25 s)
python3 -m validation.fetch_reference   # optional: re-download the raw data (needs internet)
```

Headline results with V9's Monza (full numbers in [the report](validation/reports/validation_report.md); V6's numbers for the old layout are in the [V6 docs](docs/versions/v6/IMPLEMENTATION.md)):

| Check | Baseline | Calibrated, on held-out 2025 |
|---|---|---|
| Monza length | built to the official 5793 m (V6 layout: +107 m) | — |
| Qualifying lap (4 teams), MAE | 8.9 s (≈ 11 % slow) | 0.56 s, but the fastest team is wrong |
| Pit loss against the measured median | −3.4 s | +0.26 s |
| Winner's race time | +8.2 % | −1.9 % |
| 28 circuits vs their race lap records (sanity check) | — | median −5.9 %, range −17.6 % to +2.3 % |

The calibrated grip (2.48 since V9, 2.94 in V6) is an **effective** value that absorbs other model errors; it is not a real tyre property. The simulator defaults are unchanged; the RL environment uses the calibrated values since V9. See [V6 IMPLEMENTATION.md](docs/versions/v6/IMPLEMENTATION.md) for what can and cannot be validated.

## RL environment (V7)

`rl/env.py` needs no extra installation: it uses the standard library only. Its signatures follow Gymnasium, so a `gymnasium.Env` wrapper can be added later.

- **One episode** is one race. The agent controls one car's pit stops.
- **Decision point:** once per lap, 300 m before the line, the agent chooses:

  | Action | Meaning |
  |---|---|
  | 0 | stay out |
  | 1 | pit for soft |
  | 2 | pit for medium |
  | 3 | pit for hard |
  | 4 | pit for intermediate |
  | 5 | pit for wet |

  `info["action_mask"]` says which actions are allowed; pitting is not allowed on the last lap.
- **Observation:** a `NamedTuple` of 19 floats in [0, 1]:
  - progress;
  - fitted compound (one-hot) and its wear;
  - fuel;
  - stops made, and whether the two-compound rule is met;
  - flag (one-hot);
  - wetness and rain;
  - position and gaps.

  It contains no scenario forecast and nothing about rivals' plans.
- **Reward:** −(time since the last call) ÷ one reference lap. The final step includes penalties, so the episode return is −(race time + penalties) ÷ reference lap. `terminated` means the car finished; `truncated` means `max_steps` was reached.
- **Randomness:** `reset(seed=s)` reproduces the whole episode. Each race draws conditions the agent is never told and only sees the effects of:

  | Hidden condition | Distribution | Basis |
  |---|---|---|
  | VSC or Safety Car | the circuit's chance (0.5; street circuits 0.7; Singapore 0.9), at a random time, 60–150 s | V7; F1-Encyclopedia: SC very likely on street circuits |
  | Rain shower | the circuit's chance (0.25; wet-prone 0.4; desert 0.05), random start, length and intensity | V7; F1-Encyclopedia's wet-prone list |
  | Pit loss | circuit value ± 2.5 s (Monza 25.62 s measured in V6; others 22.5 s) | V6; F1-Encyclopedia: ~20–25 s |
  | Fuel burn | 0.32 kg/km × lap length × (1 ± 8 %); the car is fuelled for the worst case | assumption under the 110 kg limit |
  | Tyre wear | every compound's wear × circuit factor (1.2 at the encyclopedia's tyre-demanding circuits, 0.8 at Albert Park) × (1 ± 25 %) | assumption |

  `info["scenario"]` records them for analysis. Policies are given only the observation and the action mask.

```python
from rl.env import StrategyEnv
from rl.policies import RuleBased

env = StrategyEnv(laps=10)          # defaults: Monza, McLaren, mediums, calibrated grip, hidden conditions, alone
policy = RuleBased()
observation, info = env.reset(seed=16)
done, total = False, 0.0
while not done:
    observation, reward, terminated, truncated, info = env.step(policy(observation, info["action_mask"]))
    total += reward
    done = terminated or truncated
print(info["total_time"], info["pit_stops"], total)   # 855.9481806437545 [(4, 'hard')] -10.864...
```

To evaluate and experiment (each 53-lap episode takes about 1.5–2 s):

```bash
python3 -m rl.evaluate --laps 53 --seeds 20   # 4 baselines on seeds 100-119: mean, std, min, max, paired difference to rule-based
python3 -m rl.experiment                      # tune RuleBased's 4 thresholds with the cross-entropy method on seeds 0-2,
                                              # then evaluate on seeds 100-119 -> rl/reports/experiment_report.md (about 7 min)
```

Result of the committed experiment, re-run in V9 with the calibrated grip and hidden conditions ([report](rl/reports/experiment_report.md)), on 20 held-out races:

| Policy | Compared with the hand-set rule-based policy | V7 (old settings) |
|---|---|---|
| fixed one-stop | +2.8 ± 12.2 s, worse on 12 of 20 | +4.2 ± 12.7 s |
| stay out | +27.2 s | +40.7 s |
| random | +149.5 s | +164 s |
| CEM-tuned version of the rule-based policy | identical: no better thresholds found on the 3 training races | +0.2 ± 5.4 s |

## Strategy research (V8)

The experiment code is in `research/`. It reuses the V7 environment unchanged and needs no extra dependencies.

**Question:** does the mix of race types used for tuning decide whether tuning the rule-based policy's 4 thresholds beats the hand-set rule?

**Design:**
- two training designs with the same budget of 6 races per candidate:
  - random draws;
  - stratified: 2 quiet, 2 with a VSC or Safety Car, 2 wet;
- 3 cross-entropy runs per design;
- 40 held-out races;
- paired bootstrap 95 % confidence intervals;
- a decision rule fixed in the config before running;
- a sensitivity re-run with a fixed pit loss (V8: 25.62 s; since V9, the old placeholder of 22 s, because the main run now draws a hidden pit loss around 25.62 s).

```bash
python3 -m research.scenario_coverage                            # about 30-40 min on 7 processes -> research/results/scenario_coverage.{json,md}
python3 -m research.scenario_coverage research/configs/smoke.json   # about 20 s pipeline check (not a result)
python3 test_research.py                                         # includes "stored results match this code (digest), config and report"
```

**Findings**, re-run in V9 on the corrected environment (this simulator only; see the [report](research/results/scenario_coverage.md), [V9 IMPLEMENTATION.md §8](docs/versions/v9/IMPLEMENTATION.md#8-results), and [V8 IMPLEMENTATION.md](docs/versions/v8/IMPLEMENTATION.md) for the original run):

| Comparison with the hand-set rule, 40 held-out races, hidden pit loss | Mean difference | 95 % CI | Verdict |
|---|---|---|---|
| Tuned, random training (3 runs) | 0.00 to +2.36 s | none below 0 (one above) | does not help |
| Tuned, stratified training (3 runs) | +0.09 to +0.77 s | none below 0 | does not help |
| Fixed one-stop | −0.25 s | [−2.67, +2.26] | no difference |
| Fixed one-stop, pit loss fixed at the old 22 s | +2.84 s | [+0.24, +5.84] | worse, almost all in wet races |

1. **Negative result, confirmed.** Neither training design made tuning beat the hand-set rule, before or after the correction.
2. **The tuning overfits.** Runs gained up to 3.4 s per race on their training races and lost 0.1–0.8 s per race on held-out races.
3. **V7/V8's "the rule beats a fixed one-stop" came from the 22 s placeholder pit loss.** With the measured, randomised pit loss the difference disappears. At 22 s, extra stops in the rain pay; at about 25.6 s they do not (8 wet races only).

Hierarchical and multi-agent RL were not attempted. The simulator exposes no lower-level decisions, and with a time-based reward rival agents barely affect each other (IMPLEMENTATION.md §3).

Options: `StrategyEnv(laps, team, start_compound, pit_loss, neutralisation_chance, rain_chance, opponents=0-3, two_compound_rule, max_steps, dt, seed, track, calibration)`. `laps`, `neutralisation_chance` and `rain_chance` default to the circuit's values. `pit_loss=None` (default) makes it hidden and random; a number fixes it. `calibration="baseline"` restores V7's grip of 1.8.

V6 found the model's lap times, pit loss and tyre and fuel effects to be off or unvalidated, so anything learned here describes **this simulator**, not real F1. See [V7 IMPLEMENTATION.md](docs/versions/v7/IMPLEMENTATION.md).

## Testing

```bash
python3 test_simulation.py      # V0 physics + V0 lap-time regression
python3 test_race.py            # V1 race behaviour (run with fuel and wear off) + V1 result regression
python3 test_tyres_fuel_pits.py # V2 tyres, fuel, pit stops, strategies + V2 result regression (traffic off)
python3 test_traffic.py         # V3 drivers, nearby cars, dirty air, DRS, overtaking + V3 result regression
python3 test_weather.py         # V4 weather state, wetting/drying, wet grip, tyre suitability, rain mid-race
python3 test_race_control.py    # V5 flags and transitions, VSC/SC, retirements, penalties, event order + V4/V5 regression
python3 test_validation.py      # V6 reference data, metrics, calibration reproducibility, report up to date
python3 test_rl.py              # V7 environment API, masks, rewards, termination/truncation, seeding, baselines
python3 test_research.py        # V8 config validation, runner, statistics, CEM, decision rule, failures, stored results
python3 test_tracks.py          # V9 segment types, banking physics, radius rule, all 28 circuits
python3 test_drivers.py         # P2-V1 driver profile: defaults, validation, attack/defence, profile-only skills
```

Each file prints `ok` when all its tests pass. An assertion error means a test failed. The tests are plain `test_*` functions using only the standard library.

## Project layout

| File | Contents |
|---|---|
| `abstract_classes.py` | `CarSpecification`, `Car`, `TrackSegment` (with `banking`, `points()`), `Straight`, `Corner`, `Hairpin`, `Spiral`, `Chicane`, `Esses`, `Track`, `TyreCompound` |
| `cars.py` | `CARS`: placeholder car designs per team |
| `tracks.py` | `CIRCUITS` (28 approximate real circuits), the builders `turn`, `hairpin`, `chicane`, `esses`, `spiral`, `straight`, `radius_for`; `MonzaV0` |
| `physics.py` | Aerodynamic force, corner speed limit, acceleration and braking (grip is an input) |
| `simulation.py` | `track_points`, `simulate_lap` (V0 flying lap) |
| `tyres.py` | `Compound`, `COMPOUNDS`, `DRY_COMPOUNDS`, `Tyres` (wear, wet grip), `best_compound` |
| `strategy.py` | `PitStop`, `Strategy` |
| `drivers.py` | `Driver` (pace, racecraft; P2-V1: attack, defence, tyre_management, consistency, wet_weather) |
| `weather.py` | `WeatherPoint`, `Conditions`, `Weather` (timeline, wetness, track temperature) |
| `traffic.py` | `TrafficRules` and rule functions: dirty air, DRS, overtaking |
| `race_control.py` | `Flag`, `RaceControlRules`, `Incident`, `Penalty`, `ControlEvent`, `RaceControl` |
| `race.py` | `RaceCar`, `OvertakeEvent`, `WeatherEvent`, `PitEvent`, `LapProfile`, `Race` |
| `main.py` | Entry point |
| `research/` | V8: `config`, `runner`, `stats`, `cem`, `scenario_coverage`, `configs/`, `results/` |
| `rl/` | V7: `env` (StrategyEnv), `policies` (baselines), `evaluate`, `experiment`, `reports/` |
| `validation/` | V6 tooling: `fetch_reference`, `reference` (load/convert), `metrics`, `model`, `calibrate`, `evaluate`, `config/`, `reports/` |
| `data/reference/` | V6 reference data (raw API responses), its provenance and its own licence (`LICENSE.md`) |
| `NOTICE` | Third-party material and credits |
| `test_*.py` | Tests |

## Version documentation

| Version | Docs |
|---|---|
| V0 | Baseline; no separate docs. Summarised in [V1 IMPLEMENTATION.md §3](docs/versions/v1/IMPLEMENTATION.md#3-inherited-v0-model-unchanged-summarised-so-v1-makes-sense). |
| V1 | [Implementation](docs/versions/v1/IMPLEMENTATION.md) · [Code flow](docs/versions/v1/CODE_FLOW.md) · [Changelog](docs/versions/v1/CHANGELOG.md) |
| V2 | [Implementation](docs/versions/v2/IMPLEMENTATION.md) · [Code flow](docs/versions/v2/CODE_FLOW.md) · [Changelog](docs/versions/v2/CHANGELOG.md) |
| V3 | [Implementation](docs/versions/v3/IMPLEMENTATION.md) · [Code flow](docs/versions/v3/CODE_FLOW.md) · [Changelog](docs/versions/v3/CHANGELOG.md) |
| V4 | [Implementation](docs/versions/v4/IMPLEMENTATION.md) · [Code flow](docs/versions/v4/CODE_FLOW.md) · [Changelog](docs/versions/v4/CHANGELOG.md) |
| V5 | [Implementation](docs/versions/v5/IMPLEMENTATION.md) · [Code flow](docs/versions/v5/CODE_FLOW.md) · [Changelog](docs/versions/v5/CHANGELOG.md) |
| V6 | [Implementation](docs/versions/v6/IMPLEMENTATION.md) · [Code flow](docs/versions/v6/CODE_FLOW.md) · [Changelog](docs/versions/v6/CHANGELOG.md) |
| V7 | [Implementation](docs/versions/v7/IMPLEMENTATION.md) · [Code flow](docs/versions/v7/CODE_FLOW.md) · [Changelog](docs/versions/v7/CHANGELOG.md) |
| V8 | [Implementation](docs/versions/v8/IMPLEMENTATION.md) · [Code flow](docs/versions/v8/CODE_FLOW.md) · [Changelog](docs/versions/v8/CHANGELOG.md) |
| V9 | [Implementation](docs/versions/v9/IMPLEMENTATION.md) · [Code flow](docs/versions/v9/CODE_FLOW.md) · [Changelog](docs/versions/v9/CHANGELOG.md) |

## Roadmap

All planned versions (V0–V8) are implemented, and V9 was added on request. That does not mean the simulator is complete or validated. The circuits are approximations, only Monza is calibrated against real timing data, and most tyre, fuel, traffic, weather and race-control parameters are unvalidated assumptions. Since V9 these assumptions enter the RL environment as random ranges, not fixed values.

## Licence and credits

- **Code:** Apache License 2.0 ([LICENSE](LICENSE)). It is open source, and you may use, change and share it, including commercially.
- **Timing data:** the files in `data/reference/raw/` (and the values reproduced from them in the validation report and `validation/config/calibrated.json`) come from the [Jolpica-F1](https://github.com/jolpica/jolpica-f1) project and its contributors (the Ergast-compatible API). They are under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/): credit required, non-commercial use only, adaptations under the same licence. See [data/reference/LICENSE.md](data/reference/LICENSE.md). Learning, research and portfolio use are non-commercial. For commercial use, Jolpica-F1's terms say to ask its maintainers.
- **Circuit information:** [F1-Encyclopedia](https://github.com/LordZeusIsBack/F1-Encyclopedia) by **LordZeusIsBack** supplied the circuit lengths, race distances, corner types and estimated corner speeds. Wikipedia filled gaps and corrected some values. Details are in [NOTICE](NOTICE) and `tracks.py`.

This is a summary, not legal advice.
