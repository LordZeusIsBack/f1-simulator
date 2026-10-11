# F1 Strategist

A Python simulation of Formula 1 cars racing around a track. It grows one small, documented version at a time, towards a platform for race-strategy and reinforcement-learning experiments.

The physics, car parameters and track geometry are **simplified approximations**. Results are not validated against real F1 data; see the limitations in each version's docs.

## Current version: V1 — multi-car race simulation

- **V0:** a simplified physics model computes a flying-lap speed profile and lap time for one car.
- **V1 (new):** several cars, two per team, start from a grid and race a set number of laps on that profile. The program reports positions, laps and gaps.

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
python3 main.py        # V0 flying-lap table, then a 53-lap race at Monza
python3 main.py 5      # same, but a 5-lap race
uv run main.py         # the same through uv
```

The output shows:

- the V0 lap time per team;
- the standings after the leader's first lap (gaps in metres);
- the final classification (gaps in seconds).

## Testing

```bash
python3 test_simulation.py   # V0 physics + V0 lap-time regression check
python3 test_race.py         # V1 race tests
```

Each file prints `ok` when all its tests pass. An assertion error means a test failed. The tests are plain `test_*` functions using only the standard library.

## Project layout

| File | Contents |
|---|---|
| `abstract_classes.py` | `CarSpecification`, `Car`, `TrackSegment`, `Straight`, `Corner`, `Track`, `TyreCompound` |
| `cars.py` | `CARS`: placeholder car designs per team |
| `tracks.py` | `Monza` built from straights and corners |
| `physics.py` | Aerodynamic force, corner speed limit, acceleration and braking |
| `simulation.py` | `track_points`, `simulate_lap` (V0 flying lap) |
| `race.py` | `RaceCar`, `LapProfile`, `Race` (V1 multi-car race) |
| `main.py` | Entry point |
| `test_simulation.py`, `test_race.py` | Tests |

## Version documentation

| Version | Docs |
|---|---|
| V0 | Baseline; no separate docs. V1's [IMPLEMENTATION.md](docs/versions/v1/IMPLEMENTATION.md#3-inherited-v0-model-unchanged-summarised-so-v1-makes-sense) summarises it. |
| V1 | [Implementation](docs/versions/v1/IMPLEMENTATION.md) · [Code flow](docs/versions/v1/CODE_FLOW.md) · [Changelog](docs/versions/v1/CHANGELOG.md) |

## Roadmap

V2 tyres, fuel and pit strategy · V3 traffic and overtaking · V4 weather · V5 race control and incidents · V6 calibration and validation · V7 reinforcement-learning interface · V8 advanced strategy research.
