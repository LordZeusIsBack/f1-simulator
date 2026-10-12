# F1 Strategist

A Python simulation of Formula 1 cars racing around a track. It grows one small, documented version at a time, towards a platform for race-strategy and reinforcement-learning experiments.

The physics, car parameters, track geometry, tyre and fuel values, and traffic rules are **simplified placeholders**. Results are not validated against real F1 data; see the limitations in each version's docs.

## Current version: V3 — traffic, overtaking, DRS and driver attributes

- **V0:** a simplified physics model computes a flying-lap speed profile and lap time for one car.
- **V1:** several cars start from a grid and race a set number of laps, with positions, laps and gaps.
- **V2:** tyres wear and lose grip, and fuel burns off and makes the car lighter. Cars pit to change tyres and/or refuel, following a fixed strategy.
- **V3 (new):** cars interact:
  - dirty air costs pace in corners;
  - DRS helps on long straights;
  - a car can only pass on a straight with enough speed advantage, otherwise it is held up behind.

  Drivers have `pace` and `racecraft`. Every pass and refused attempt is logged.

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
python3 main.py        # V0 lap table, then a 53-lap Monza race with traffic (about 19 s)
python3 main.py 10     # a 10-lap race (at least 2 laps, so the one-stop plan fits)
uv run main.py         # the same through uv
```

Each team runs one car on **"no stop (M)"** and one on **"1 stop (M-H)"**, so the two plans meet on identical cars. The program prints:

- the standings after lap 1;
- the final classification, with a strategy column;
- the pit-stop log: lap, time, old tyres and their wear, new tyres, fuel added, stop duration;
- the overtake log: each pass with the speed advantage, the margin needed and DRS, plus how often cars were held up.

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
- wet tyres;
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

To reproduce V1 behaviour, use `fuel_per_lap=0.0`, `compounds={TyreCompound.MEDIUM: Compound(TYRE_GRIP, 0.0)}` and `traffic=None`. To reproduce V2, use `traffic=None`.

## Strategy comparison example

The same car (McLaren) runs alone over 53 laps of Monza with default settings, once per plan. The run is deterministic and takes about 9 s:

```bash
python3 - <<'EOF'
from abstract_classes import TyreCompound as T
from cars import CARS
from race import FUEL_PER_LAP, Race, RaceCar
from strategy import PitStop, Strategy
from tracks import Monza

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
    race = Race(Monza(), laps, [car])
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
from tracks import Monza

for traffic in ("on", "off"):
    grid = [
        RaceCar(1, "Mercedes", CARS["Mercedes"], driver=Driver("Defender", racecraft=0.9)),
        RaceCar(2, "McLaren", CARS["McLaren"], driver=Driver("Rookie", racecraft=0.1)),
        RaceCar(3, "McLaren", CARS["McLaren"], driver=Driver("Veteran", racecraft=0.9)),
    ]
    race = Race(Monza(), 6, grid, **({} if traffic == "on" else {"traffic": None}))
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

## Testing

```bash
python3 test_simulation.py      # V0 physics + V0 lap-time regression
python3 test_race.py            # V1 race behaviour (run with fuel and wear off) + V1 result regression
python3 test_tyres_fuel_pits.py # V2 tyres, fuel, pit stops, strategies + V2 result regression (traffic off)
python3 test_traffic.py         # V3 drivers, nearby cars, dirty air, DRS, overtaking
```

Each file prints `ok` when all its tests pass. An assertion error means a test failed. The tests are plain `test_*` functions using only the standard library.

## Project layout

| File | Contents |
|---|---|
| `abstract_classes.py` | `CarSpecification`, `Car`, `TrackSegment`, `Straight`, `Corner`, `Track`, `TyreCompound` |
| `cars.py` | `CARS`: placeholder car designs per team |
| `tracks.py` | `Monza` built from straights and corners |
| `physics.py` | Aerodynamic force, corner speed limit, acceleration and braking (grip is an input) |
| `simulation.py` | `track_points`, `simulate_lap` (V0 flying lap) |
| `tyres.py` | `Compound`, `COMPOUNDS`, `Tyres` (wear and grip) |
| `strategy.py` | `PitStop`, `Strategy` |
| `drivers.py` | `Driver` (pace, racecraft) |
| `traffic.py` | `TrafficRules` and rule functions: dirty air, DRS, overtaking |
| `race.py` | `RaceCar`, `OvertakeEvent`, `PitEvent`, `LapProfile`, `Race` |
| `main.py` | Entry point |
| `test_*.py` | Tests |

## Version documentation

| Version | Docs |
|---|---|
| V0 | Baseline; no separate docs. Summarised in [V1 IMPLEMENTATION.md §3](docs/versions/v1/IMPLEMENTATION.md#3-inherited-v0-model-unchanged-summarised-so-v1-makes-sense). |
| V1 | [Implementation](docs/versions/v1/IMPLEMENTATION.md) · [Code flow](docs/versions/v1/CODE_FLOW.md) · [Changelog](docs/versions/v1/CHANGELOG.md) |
| V2 | [Implementation](docs/versions/v2/IMPLEMENTATION.md) · [Code flow](docs/versions/v2/CODE_FLOW.md) · [Changelog](docs/versions/v2/CHANGELOG.md) |
| V3 | [Implementation](docs/versions/v3/IMPLEMENTATION.md) · [Code flow](docs/versions/v3/CODE_FLOW.md) · [Changelog](docs/versions/v3/CHANGELOG.md) |

## Roadmap

V4 weather · V5 race control and incidents · V6 calibration and validation · V7 reinforcement-learning interface · V8 advanced strategy research.
