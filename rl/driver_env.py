"""A driving environment (P2-V4) with reset()/step(), built on the P2-V3 controlled car. Separate from the strategist's
StrategyEnv (rl/env.py): no pit calls here, and the strategist environment is unchanged.

One episode = one race of `laps` laps. The agent drives one car (the ego car, moved by pedals and physics) behind or
among `opponents` cars that follow their lap profiles. Every DECISION_DISTANCE metres it picks a P2-V2 DriverAction,
which the P2-V3 controller carries out as a grip share; P2-V2's availability rule masks ATTACK (no car ahead) and
DEFEND (no car behind). Dry, no race control, no pit stops. Stdlib only; Gymnasium-style signatures:
reset() -> (observation, info), step(action) -> StepResult(observation, reward, terminated, truncated, info).

The driver's skills are environment settings, not observations: the agent learns to drive one fixed driver, and the
skills shape how the car responds (pace, attack/defence in the passing rule, tyre_management in the wear rate).
"""
import random
from typing import NamedTuple

from abstract_classes import TyreCompound
from cars import CARS
from control import CarControl
from drivers import Driver
from driving import DriverAction, available_actions, observe
from physics import TYRE_GRIP
from race import FUEL_PER_KM, LapProfile, Race, RaceCar
from strategy import Strategy
from tracks import CIRCUITS
from traffic import TrafficRules
from tyres import COMPOUNDS
from validation.model import load_config

ACTIONS = tuple(DriverAction)  # index -> action: 0 MAINTAIN_PACE, 1 ATTACK, 2 DEFEND, 3 CONSERVE_TYRES
DECISION_DISTANCE = 250.0  # m between decisions (~3 s at Monza), model choice
SPEED_SCALE = 100.0  # m/s: speed is reported as min(speed / SPEED_SCALE, 1)
GAP_SCALE = 3.0  # s: gaps are reported as min(gap / GAP_SCALE, 1); 1 when there is no such car
CLOSING_SCALE = 10.0  # m/s: closing speed is reported as clip(closing / CLOSING_SCALE, -1, 1); 0 with no car ahead
WEAR_PRICE = 130.0  # s per unit of tyre wear (0 = new, 1 = fully worn): what tyre life is worth after this race;
# placeholder chosen so that no fixed style is best (probe seeds 500-511, outside training and evaluation)


class Observation(NamedTuple):
    """What the agent sees at each decision: the P2-V2 driver observation, normalised. Floats in [0, 1] (closing in
    [-1, 1]). Nothing about the rivals' skills, the scenario draw or the driver's own skill values."""
    progress: float  # metres covered / race distance
    speed: float  # own speed / SPEED_SCALE
    on_straight: float  # 1 on a straight (where a pass can start)
    gap_ahead: float  # time to the car ahead / GAP_SCALE, 1 if none
    closing: float  # own speed − ahead's speed at this spot, / CLOSING_SCALE; > 0 = faster than the car ahead
    gap_behind: float  # time of the car behind / GAP_SCALE, 1 if none
    held_up: float  # 1 while the passing rule keeps this car behind the car ahead
    drs: float  # 1 if DRS is usable on this lap
    tyre_wear: float  # 0 = new, 1 = fully worn, including this lap so far
    position: float  # (position − 1) / (cars − 1)


class StepResult(NamedTuple):
    observation: Observation
    reward: float  # −(seconds lost against the ideal lap + wear_price × wear added) over this step
    terminated: bool  # the ego car finished
    truncated: bool  # stopped early by max_steps
    info: dict


class DriverEnv:
    """Driving environment for one car. See docs/phase2/p2-v4/IMPLEMENTATION.md."""

    def __init__(
        self,
        laps: int = 5,
        track: str = "Monza",
        team: str = "McLaren",
        driver: Driver = Driver("Agent"),
        opponents: int = 3,
        wear_price: float = WEAR_PRICE,
        dt: float = 0.25,
        max_steps: int | None = None,
        seed: int | None = None,
        calibration: str = "calibrated",  # validation/config/<name>.json: "baseline" gives grip 1.8
    ):
        if track not in CIRCUITS:
            raise ValueError(f"track must be one of {sorted(CIRCUITS)}")
        if team not in CARS:
            raise ValueError(f"team must be one of {sorted(CARS)}")
        if not isinstance(laps, int) or isinstance(laps, bool) or laps < 1:
            raise ValueError("laps must be an integer >= 1")
        if not isinstance(driver, Driver):
            raise ValueError("driver must be a drivers.Driver")
        if opponents not in range(len(CARS)):
            raise ValueError(f"opponents must be 0-{len(CARS) - 1}")
        if not 0 <= wear_price < float("inf") or not 0 < dt <= 1.0:
            raise ValueError("need 0 <= wear_price < inf and 0 < dt <= 1 s")
        if max_steps is not None and (not isinstance(max_steps, int) or max_steps < 1):
            raise ValueError("max_steps must be None or an integer >= 1")
        self.track = CIRCUITS[track]()  # one instance per environment, so profiles and envelopes are cached
        self.laps, self.team, self.driver, self.opponents = laps, team, driver, opponents
        self.wear_price, self.dt, self.max_steps = wear_price, dt, max_steps
        scale = load_config(calibration)["tyre_grip"] / TYRE_GRIP  # as StrategyEnv: every compound's grip scaled
        self.compounds = {compound: spec._replace(grip=spec.grip * scale) for compound, spec in COMPOUNDS.items()}
        self.fuel_per_lap = FUEL_PER_KM * self.track.length / 1000  # kg
        fuel = laps * self.fuel_per_lap
        # ideal lap of the ego car on new tyres with the start fuel: the reference for "seconds lost"
        self.reference = LapProfile(CARS[team], self.track, self.compounds[TyreCompound.MEDIUM].grip, fuel)
        self._rng = random.Random(seed)
        self._race = None

    # ---- episode control -------------------------------------------------------------------------------------

    def reset(self, seed: int | None = None, options: dict | None = None) -> tuple[Observation, dict]:
        """Start a new race. With a seed, the episode (grid and rivals' drivers, then everything after) is reproducible."""
        if seed is not None:
            self._rng = random.Random(seed)
        rng, fuel = self._rng, self.laps * self.fuel_per_lap
        rivals = [team for team in CARS if team != self.team][: self.opponents]
        drivers = [Driver(f"Rival {n}", pace=round(rng.uniform(0.0, 1.0), 2), racecraft=round(rng.uniform(0.0, 1.0), 2))
                   for n in range(1, len(rivals) + 1)]
        self._car = RaceCar(1, self.team, CARS[self.team], Strategy(TyreCompound.MEDIUM, fuel), self.driver,
                            control=CarControl())
        grid = [RaceCar(n, team, CARS[team], Strategy(TyreCompound.MEDIUM, fuel), driver)
                for n, (team, driver) in enumerate(zip(rivals, drivers), start=2)]
        slot = rng.randrange(len(grid) + 1)  # the ego car's grid slot is part of the scenario
        grid.insert(slot, self._car)
        self.scenario = {"grid": [car.number for car in grid], "slot": slot,
                         "rivals": {car.number: (car.team, car.driver.pace, car.driver.racecraft)
                                    for car in grid if car is not self._car}}
        self._race = Race(self.track, self.laps, grid, fuel_per_lap=self.fuel_per_lap, compounds=self.compounds,
                          traffic=TrafficRules() if self.opponents else None)
        self._steps, self._done, self._passes = 0, False, 0
        self._next = self._car.distance + DECISION_DISTANCE
        return self._observe(), self._info(0.0, 0.0)

    def step(self, action: int) -> StepResult:
        """Drive with `action` for the next DECISION_DISTANCE metres (or to the finish), then score that stretch."""
        if self._race is None or self._done:
            raise RuntimeError("call reset() before step(), and again after an episode ends")
        if not isinstance(action, int) or isinstance(action, bool) or not 0 <= action < len(ACTIONS):
            raise ValueError(f"action must be an integer 0-{len(ACTIONS) - 1}, got {action!r}")
        if not self.action_mask()[action]:
            raise ValueError(f"action {action} ({ACTIONS[action].name}) is not available now; see info['action_mask']")
        race, car = self._race, self._car
        car.control.action = ACTIONS[action]
        time, distance, wear = race.time, car.distance, self.tyre_wear()
        overtakes = len(race.overtakes)
        while car.finish_time is None and car.distance < self._next:
            race.step(self.dt)
        self._next += DECISION_DISTANCE
        self._passes += sum(e.outcome == "passed" and e.attacker == car.number for e in race.overtakes[overtakes:])
        end = car.finish_time if car.finish_time is not None else race.time
        time_lost = (end - time) - (self.reference.time_at(car.distance) - self.reference.time_at(distance))
        wear_cost = self.wear_price * (self.tyre_wear() - wear)
        self._steps += 1
        terminated = car.finish_time is not None
        truncated = not terminated and self.max_steps is not None and self._steps >= self.max_steps
        self._done = terminated or truncated
        return StepResult(self._observe(), -(time_lost + wear_cost), terminated, truncated,
                          self._info(time_lost, wear_cost))

    def action_mask(self) -> tuple[bool, ...]:
        """P2-V2's rule: ATTACK needs a car ahead and DEFEND a car behind; after the finish only MAINTAIN_PACE."""
        if self._car.finish_time is not None:
            return tuple(action is DriverAction.MAINTAIN_PACE for action in ACTIONS)
        allowed = available_actions(observe(self._race, self._car))
        return tuple(action in allowed for action in ACTIONS)

    def tyre_wear(self) -> float:
        """Wear of the ego car's set now, including the part of the current lap already driven."""
        car = self._car
        used = (car.tyres.laps if car.tyres.used is None else car.tyres.used) + car.control.load / self.track.length
        return min(1.0, used * self.compounds[car.tyres.compound].wear_per_lap)

    # ---- observation and info ----------------------------------------------------------------------------------

    def _observe(self) -> Observation:
        race, car = self._race, self._car
        standings = race.standings()
        position = standings.index(car) / (len(standings) - 1) if len(standings) > 1 else 0.0
        progress = min(max(car.distance / (self.laps * self.track.length), 0.0), 1.0)
        if car.finish_time is not None:  # nothing ahead or behind any more: the race is over for this car
            return Observation(1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, self.tyre_wear(), position)
        seen = observe(race, car)
        return Observation(
            progress=progress,
            speed=min(seen.speed / SPEED_SCALE, 1.0),
            on_straight=float(seen.on_straight),
            gap_ahead=1.0 if seen.gap_ahead is None else min(seen.gap_ahead / GAP_SCALE, 1.0),
            closing=0.0 if seen.closing_speed is None else max(-1.0, min(seen.closing_speed / CLOSING_SCALE, 1.0)),
            gap_behind=1.0 if seen.gap_behind is None else min(seen.gap_behind / GAP_SCALE, 1.0),
            held_up=float(car.held_by is not None),
            drs=float(seen.drs),
            tyre_wear=self.tyre_wear(),
            position=position,
        )

    def _info(self, time_lost: float, wear_cost: float) -> dict:
        race, car = self._race, self._car
        return {
            "lap": car.laps,
            "distance": car.distance,
            "race_time": race.time,
            "finish_time": car.finish_time,
            "position": race.standings().index(car) + 1,
            "passes": self._passes,
            "passed_by": sum(e.outcome == "passed" and e.defender == car.number for e in race.overtakes),
            "tyre_wear": self.tyre_wear(),
            "clipped": car.control.clipped,
            "time_lost": time_lost,  # s against the ideal lap over the last step
            "wear_cost": wear_cost,  # s-equivalent over the last step
            "action_mask": self.action_mask(),
            "driver_observation": observe(race, car) if car.finish_time is None else None,  # for P2-V2 policies
            "scenario": self.scenario,
        }
