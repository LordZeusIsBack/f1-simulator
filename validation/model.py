"""Run the simulator for one parameter configuration. Parameters are passed in; no simulator code or global changes."""
import json
from pathlib import Path

from abstract_classes import TyreCompound
from cars import CARS
from physics import TYRE_GRIP
from race import FUEL_PER_LAP, Race, RaceCar
from simulation import simulate_lap
from strategy import PitStop, Strategy
from tracks import Monza
from tyres import COMPOUNDS

CONFIG = Path(__file__).resolve().parent / "config"


def load_config(name: str, folder: Path = CONFIG) -> dict:
    """<folder>/<name>.json, checked: tyre_grip > 0, pit_loss >= 0."""
    config = json.loads((folder / f"{name}.json").read_text())
    for key in ("tyre_grip", "pit_loss"):
        if not isinstance(config.get(key), (int, float)) or isinstance(config.get(key), bool):
            raise ValueError(f"{name}: {key} must be a number")
    if config["tyre_grip"] <= 0 or config["pit_loss"] < 0:
        raise ValueError(f"{name}: need tyre_grip > 0 and pit_loss >= 0")
    return config


def flying_laps(config: dict, teams, track=None) -> dict[str, float]:
    """s: the V0 flying lap of each team's model car (at Monza unless another track is given), no fuel, with the
    configured grip."""
    track = track or Monza()
    return {team: simulate_lap(CARS[team], track, config["tyre_grip"])[0] for team in teams}


def race_time(config: dict, team: str, laps: int, stop_laps: list[int]) -> float:
    """s: one model car racing alone at Monza, pitting on the given laps.

    The reference data has no tyre compounds, so the car is assumed to start on mediums and fit hards at each stop.
    All compound grips are scaled by tyre_grip / TYRE_GRIP, so the baseline config reproduces the V2-V5 table."""
    scale = config["tyre_grip"] / TYRE_GRIP
    compounds = {compound: spec._replace(grip=spec.grip * scale) for compound, spec in COMPOUNDS.items()}
    stops = tuple(PitStop(lap, TyreCompound.HARD) for lap in stop_laps)
    car = RaceCar(1, team, CARS[team], Strategy(TyreCompound.MEDIUM, laps * FUEL_PER_LAP, stops))
    race = Race(Monza(), laps, [car], pit_loss=config["pit_loss"], compounds=compounds, traffic=None)
    race.run(0.5)
    return car.finish_time
