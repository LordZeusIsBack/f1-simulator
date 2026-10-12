"""A race-strategy environment with reset()/step(), built on the public simulator API.

One episode = one race. The agent controls the pit decisions of one car: once per lap, DECISION_DISTANCE before the
car reaches the line (the "box or stay out" call before pit entry), it chooses to stay out or to pit at that line for
a given compound. Everything else (driving, traffic, weather, race control) is the V1-V5 simulator. Stdlib only; the signatures follow the
Gymnasium convention: reset() -> (observation, info), step(action) -> (observation, reward, terminated, truncated, info).

Since V9 the race runs on any circuit in tracks.CIRCUITS with the V6 calibrated grip, and every race draws hidden
conditions the agent never observes directly: pit loss, fuel burn rate, tyre wear rate, and (as in V7) whether and when
a VSC/safety car or a shower comes. The agent only sees their effects (fuel level, tyre wear, flags, wetness).
info["scenario"] records them for analysis; a policy given info would be told the hidden values.
"""
import random
from typing import NamedTuple

from abstract_classes import TyreCompound
from cars import CARS
from physics import TYRE_GRIP
from race import FUEL_CAPACITY, FUEL_PER_KM, Race, RaceCar
from race_control import Flag, Incident, RaceControl, RaceControlRules
from simulation import simulate_lap
from strategy import PitStop, Strategy
from tracks import CIRCUITS
from traffic import TrafficRules
from tyres import COMPOUNDS
from validation.model import load_config
from weather import Weather, WeatherPoint

# action 0 = stay out; action i > 0 = pit at the end of this lap for COMPOUND_ORDER[i - 1]
COMPOUND_ORDER = (TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD, TyreCompound.INTERMEDIATE, TyreCompound.WET)
ACTIONS = ("stay out", *(f"pit for {compound.value}" for compound in COMPOUND_ORDER))
GAP_SCALE = 30.0  # s: gaps are reported as min(gap / GAP_SCALE, 1)
RAIN_SCALE = 10.0  # mm/h: rain is reported as min(rain / RAIN_SCALE, 1)
MAX_STOPS = 3  # stops are reported as min(stops / MAX_STOPS, 1)
DECISION_DISTANCE = 300.0  # m before the line at which the pit call is made, model assumption
GENERIC_PIT_LOSS = 22.5  # s, circuits without a measured pit loss: middle of F1-Encyclopedia's ~20-25 s (12, 16.5)
PIT_LOSS_SPREAD = 2.5  # s, hidden pit loss = circuit value +- this, uniform
FUEL_SPREAD = 0.08  # hidden burn rate = nominal x (1 +- this); the car is fuelled for the worst case
WEAR_SPREAD = 0.25  # hidden tyre wear = circuit factor x (1 +- this), on every compound


class Observation(NamedTuple):
    """What the strategist sees at each pit call. Every value is a float in [0, 1]."""
    progress: float  # laps completed / race laps
    soft: float  # one-hot: compound fitted now
    medium: float
    hard: float
    intermediate: float
    wet: float
    tyre_wear: float  # the model's wear of the fitted set (an idealised, exact estimate)
    fuel: float  # kg on board / FUEL_CAPACITY
    stops: float  # min(stops made / MAX_STOPS, 1)
    two_compounds: float  # 1 if the car has used two dry compounds or any wet tyre (the V5 rule is met)
    green: float  # one-hot: race-control flag now
    yellow: float
    vsc: float
    safety_car: float
    wetness: float  # track wetness now (no forecast)
    rain: float  # min(rain now / RAIN_SCALE, 1)
    position: float  # (position - 1) / (cars - 1); 0 when racing alone
    gap_ahead: float  # min(interval to the car ahead / GAP_SCALE, 1); 1 when nobody is ahead
    gap_behind: float  # min(interval of the car behind / GAP_SCALE, 1); 1 when nobody is behind


class StepResult(NamedTuple):
    observation: Observation
    reward: float
    terminated: bool  # the ego car finished the race
    truncated: bool  # stopped early by max_steps
    info: dict


class _AgentPlan:
    """Duck-typed Strategy: the race asks it at every line crossing; it answers with the agent's pending decision."""

    def __init__(self, compound: TyreCompound, fuel: float):
        self.compound, self.fuel, self.stops, self.name = compound, fuel, (), "agent"
        self.pending: PitStop | None = None

    def planned_stop(self, lap):  # used by the race's fuel check: the agent plans no stops in advance
        return None

    def stop_after(self, lap, tyres, wetness=0.0, compounds=COMPOUNDS):
        return self.pending if self.pending is not None and self.pending.lap == lap else None


class StrategyEnv:
    """Pit-strategy environment for one car. See docs/versions/v7/IMPLEMENTATION.md and docs/versions/v9/."""

    def __init__(
        self,
        laps: int | None = None,  # None: the circuit's Grand Prix distance
        team: str = "McLaren",
        start_compound: TyreCompound = TyreCompound.MEDIUM,
        pit_loss: float | None = None,  # None: hidden, random per race; a number fixes it
        neutralisation_chance: float | None = None,  # None: the circuit's value
        rain_chance: float | None = None,  # None: the circuit's value
        opponents: int = 0,
        two_compound_rule: bool = True,
        max_steps: int | None = None,
        dt: float = 0.5,
        seed: int | None = None,
        track: str = "Monza",
        calibration: str = "calibrated",  # validation/config/<name>.json: "baseline" gives V7's grip 1.8
    ):
        if track not in CIRCUITS:
            raise ValueError(f"track must be one of {sorted(CIRCUITS)}")
        circuit = CIRCUITS[track]
        laps = circuit.laps if laps is None else laps
        neutralisation_chance = circuit.neutralisation_chance if neutralisation_chance is None else neutralisation_chance
        rain_chance = circuit.rain_chance if rain_chance is None else rain_chance
        if not isinstance(laps, int) or laps < 2:
            raise ValueError("laps must be an integer >= 2")
        if team not in CARS:
            raise ValueError(f"team must be one of {sorted(CARS)}")
        if start_compound not in COMPOUND_ORDER:
            raise ValueError(f"unknown start compound {start_compound!r}")
        if (pit_loss is not None and not pit_loss >= 0) or not dt > 0:
            raise ValueError("need pit_loss >= 0 and dt > 0")
        for chance in (neutralisation_chance, rain_chance):
            if not 0 <= chance <= 1:
                raise ValueError("chances must be in [0, 1]")
        if opponents not in range(len(CARS)):
            raise ValueError(f"opponents must be 0-{len(CARS) - 1}")
        if max_steps is not None and (not isinstance(max_steps, int) or max_steps < 1):
            raise ValueError("max_steps must be None or an integer >= 1")
        self.track = circuit()  # one instance per environment, so lap profiles are cached across races
        self.fuel_per_lap = FUEL_PER_KM * self.track.length / 1000  # kg, nominal
        self.start_fuel = laps * self.fuel_per_lap * (1 + FUEL_SPREAD)  # kg, enough at the highest burn rate
        if self.start_fuel > FUEL_CAPACITY:
            raise ValueError(f"{laps} laps of {track} need {self.start_fuel:.1f} kg, more than the {FUEL_CAPACITY} kg tank")
        self.laps, self.team, self.start_compound = laps, team, start_compound
        self.pit_loss, self.dt, self.max_steps = pit_loss, dt, max_steps
        self.neutralisation_chance, self.rain_chance = neutralisation_chance, rain_chance
        self.opponents, self.two_compound_rule = opponents, two_compound_rule
        config = load_config(calibration)
        scale = config["tyre_grip"] / TYRE_GRIP  # as validation.model: every compound's grip scaled alike
        self.compounds = {compound: spec._replace(grip=spec.grip * scale) for compound, spec in COMPOUNDS.items()}
        self.base_pit_loss = self.track.pit_loss or GENERIC_PIT_LOSS
        self.reference_lap = simulate_lap(CARS[team], self.track, config["tyre_grip"])[0]  # s, reward scale
        self._rng = random.Random(seed)
        self._race = None

    # ---- episode control -------------------------------------------------------------------------------------

    def reset(self, seed: int | None = None, options: dict | None = None) -> tuple[Observation, dict]:
        """Start a new race. With a seed, the episode (scenario and everything after it) is fully reproducible."""
        if seed is not None:
            self._rng = random.Random(seed)
        self.scenario = self._draw_scenario()
        fuel = self.start_fuel
        self._plan = _AgentPlan(self.start_compound, fuel)
        self._car = RaceCar(1, self.team, CARS[self.team], self._plan)
        rivals = [team for team in CARS if team != self.team][: self.opponents]
        grid = [self._car] + [
            RaceCar(n, team, CARS[team], Strategy(TyreCompound.MEDIUM, fuel, (PitStop(self.laps // 2, TyreCompound.HARD),),
                                                  react_to_weather=True))
            for n, team in enumerate(rivals, start=2)
        ]
        self._rng.shuffle(grid)  # the ego car's grid slot is part of the scenario
        rules = RaceControlRules() if self.two_compound_rule else RaceControlRules(two_compound_penalty=0.0)
        hidden = self.scenario["hidden"]
        compounds = {c: spec._replace(wear_per_lap=spec.wear_per_lap * hidden["tyre_wear"])
                     for c, spec in self.compounds.items()}
        self._race = Race(self.track, self.laps, grid, pit_loss=hidden["pit_loss"], fuel_per_lap=hidden["fuel_per_lap"],
                          compounds=compounds,
                          traffic=TrafficRules() if self.opponents else None,  # alone: nobody to interact with
                          weather=self.scenario["weather"], race_control=RaceControl(self.scenario["incidents"], rules=rules))
        self._steps, self._last_time, self._done = 0, 0.0, False
        self._run_to_decision()
        return self._observe(), self._info()

    def step(self, action: int) -> StepResult:
        """Apply the call for the line just ahead, run the race to the next call (or the finish), and score it."""
        if self._race is None or self._done:
            raise RuntimeError("call reset() before step(), and again after an episode ends")
        if not isinstance(action, int) or isinstance(action, bool) or not 0 <= action < len(ACTIONS):
            raise ValueError(f"action must be an integer 0-{len(ACTIONS) - 1}, got {action!r}")
        if not self.action_mask()[action]:
            raise ValueError(f"action {action} ({ACTIONS[action]}) is not allowed now; see info['action_mask']")
        car = self._car
        lap = car.laps + 1  # the lap the car is completing: the stop (if any) happens at the line just ahead
        self._plan.pending = None if action == 0 else PitStop(lap, COMPOUND_ORDER[action - 1])
        while car.laps < lap and car.finish_time is None:  # reach and cross the line (and stop, if called)
            self._race.step(self.dt)
        self._run_to_decision()
        self._steps += 1
        terminated = car.finish_time is not None
        truncated = not terminated and self.max_steps is not None and self._steps >= self.max_steps
        end = car.finish_time + car.penalty_time if terminated else self._race.time
        reward = -(end - self._last_time) / self.reference_lap
        self._last_time = end
        self._done = terminated or truncated
        return StepResult(self._observe(), reward, terminated, truncated, self._info())

    def _run_to_decision(self) -> None:
        """Run the race until the car is DECISION_DISTANCE before its next line, or has finished."""
        car, length = self._car, self._race.track.length
        while car.finish_time is None and car.distance < (car.laps + 1) * length - DECISION_DISTANCE:
            self._race.step(self.dt)

    def action_mask(self) -> tuple[bool, ...]:
        """Which actions are allowed now: staying out always; pitting unless the line ahead is the finish."""
        can_pit = self._car.laps + 1 < self.laps
        return (True, *(can_pit and compound in self._race.compounds for compound in COMPOUND_ORDER))

    # ---- scenario --------------------------------------------------------------------------------------------

    def _draw_scenario(self) -> dict:
        """Random (seeded) race conditions the agent cannot see in advance: a VSC or SC, a rain shower, the air
        temperature, then the hidden pit loss, fuel burn and tyre wear (drawn last, so V7's event draws keep their order)."""
        rng, expected = self._rng, self.laps * self.reference_lap * 1.05  # s, a rough race length
        air = round(rng.uniform(18.0, 32.0), 1)
        incidents = []
        if rng.random() < self.neutralisation_chance:
            flag = rng.choice((Flag.VSC, Flag.SAFETY_CAR))
            incidents.append(Incident(round(rng.uniform(0.15, 0.85) * expected, 1), flag,
                                      round(rng.uniform(60.0, 150.0), 1), reason="scenario"))
        weather = None
        if rng.random() < self.rain_chance:
            start = round(rng.uniform(0.1, 0.7) * expected, 1)
            length, rain = round(rng.uniform(300.0, 900.0), 1), round(rng.uniform(2.0, 10.0), 1)
            weather = Weather([WeatherPoint(0, air), WeatherPoint(start, air), WeatherPoint(start + 60, air, rain),
                               WeatherPoint(start + length, air, rain), WeatherPoint(start + length + 60, air)])
        pit_loss = round(self.base_pit_loss + rng.uniform(-PIT_LOSS_SPREAD, PIT_LOSS_SPREAD), 2)  # always drawn, so
        hidden = {  # a fixed pit loss leaves the other draws of a seed unchanged
            "pit_loss": pit_loss if self.pit_loss is None else self.pit_loss,
            "fuel_per_lap": round(self.fuel_per_lap * rng.uniform(1 - FUEL_SPREAD, 1 + FUEL_SPREAD), 4),
            "tyre_wear": round(self.track.tyre_wear * rng.uniform(1 - WEAR_SPREAD, 1 + WEAR_SPREAD), 3),
        }
        return {"incidents": incidents, "weather": weather, "air_temp": air, "hidden": hidden}

    # ---- observation and info ----------------------------------------------------------------------------------

    def _observe(self) -> Observation:
        race, car = self._race, self._car
        compound = car.tyres.compound
        stops = [event for event in race.pit_events if event.number == car.number]
        used = {self.start_compound, *(event.tyres_after.compound for event in stops)}
        wet_used = bool(used & {TyreCompound.INTERMEDIATE, TyreCompound.WET})
        flag = race.race_control.flag
        conditions = race.weather.conditions if race.weather else None
        standings = race.standings()
        position = standings.index(car)
        ahead = race.car_ahead(car) if car.finish_time is None else None
        behind = [c for c in race.cars if c is not car and race.car_ahead(c) is car] if car.finish_time is None else []
        return Observation(
            progress=car.laps / self.laps,
            **{c.value: float(compound is c) for c in COMPOUND_ORDER},
            tyre_wear=car.tyres.wear(race.compounds),
            fuel=max(0.0, min(car.fuel / FUEL_CAPACITY, 1.0)),
            stops=min(len(stops) / MAX_STOPS, 1.0),
            two_compounds=float(wet_used or len(used) >= 2),
            green=float(flag is Flag.GREEN), yellow=float(flag is Flag.YELLOW),
            vsc=float(flag is Flag.VSC), safety_car=float(flag is Flag.SAFETY_CAR),
            wetness=conditions.wetness if conditions else 0.0,
            rain=min(conditions.rain / RAIN_SCALE, 1.0) if conditions else 0.0,
            position=position / (len(standings) - 1) if len(standings) > 1 else 0.0,
            gap_ahead=min(race.interval(car, ahead) / GAP_SCALE, 1.0) if ahead else 1.0,
            gap_behind=min(race.interval(behind[0], car) / GAP_SCALE, 1.0) if behind else 1.0,
        )

    def _info(self) -> dict:
        race, car = self._race, self._car
        return {
            "lap": car.laps,
            "race_time": race.time,
            "finish_time": car.finish_time,
            "penalty_time": car.penalty_time,
            "total_time": None if car.finish_time is None else car.finish_time + car.penalty_time,
            "compound": car.tyres.compound.value,
            "pit_stops": [(e.lap, e.tyres_after.compound.value) for e in race.pit_events if e.number == car.number],
            "flag": race.race_control.flag.name,
            "action_mask": self.action_mask(),
            "scenario": {"incidents": [(i.time, i.flag.name, i.duration) for i in self.scenario["incidents"]],
                         "rain": self.scenario["weather"] is not None, "air_temp": self.scenario["air_temp"],
                         "hidden": self.scenario["hidden"]},
        }
