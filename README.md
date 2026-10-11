# F1 Strategist

A Python simulation of Formula 1 cars racing around a track. It grows one small, documented version at a time, towards a platform for race-strategy and reinforcement-learning experiments.

The physics, car parameters, track geometry, and tyre and fuel values are **simplified placeholders**. Results are not validated against real F1 data; see the limitations in each version's docs.

## Current version: V2 — tyres, fuel and pit strategy

- **V0:** a simplified physics model computes a flying-lap speed profile and lap time for one car.
- **V1:** several cars start from a grid and race a set number of laps, with positions, laps and gaps.
- **V2 (new):** tyres wear and lose grip, and fuel burns off and makes the car lighter. Cars pit to change tyres and/or refuel, following a fixed strategy. Every stop is logged.

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
python3 main.py        # V0 lap table, then a 53-lap Monza race (about 11 s)
python3 main.py 10     # a 10-lap race (at least 2 laps, so the one-stop plan fits)
uv run main.py         # the same through uv
```

Each team runs one car on **"no stop (M)"** and one on **"1 stop (M-H)"**, so the two plans meet on identical cars. The program prints:

- the standings after lap 1;
- the final classification, with a strategy column;
- the pit-stop log: lap, time, old tyres and their wear, new tyres, fuel added, stop duration.

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

To reproduce V1 behaviour, use `fuel_per_lap=0.0` and `compounds={TyreCompound.MEDIUM: Compound(TYRE_GRIP, 0.0)}`.

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

## Testing

```bash
python3 test_simulation.py      # V0 physics + V0 lap-time regression
python3 test_race.py            # V1 race behaviour (run with fuel and wear off) + V1 result regression
python3 test_tyres_fuel_pits.py # V2 tyres, fuel, pit stops, strategies
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
| `race.py` | `RaceCar`, `PitEvent`, `LapProfile`, `Race` |
| `main.py` | Entry point |
| `test_*.py` | Tests |

## Version documentation

| Version | Docs |
|---|---|
| V0 | Baseline; no separate docs. Summarised in [V1 IMPLEMENTATION.md §3](docs/versions/v1/IMPLEMENTATION.md#3-inherited-v0-model-unchanged-summarised-so-v1-makes-sense). |
| V1 | [Implementation](docs/versions/v1/IMPLEMENTATION.md) · [Code flow](docs/versions/v1/CODE_FLOW.md) · [Changelog](docs/versions/v1/CHANGELOG.md) |
| V2 | [Implementation](docs/versions/v2/IMPLEMENTATION.md) · [Code flow](docs/versions/v2/CODE_FLOW.md) · [Changelog](docs/versions/v2/CHANGELOG.md) |

## Roadmap

V3 traffic and overtaking · V4 weather · V5 race control and incidents · V6 calibration and validation · V7 reinforcement-learning interface · V8 advanced strategy research.
