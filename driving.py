"""On-track driver decisions (P2-V2): what a driver observes, the actions it can propose, and rule-based policies.

A driving policy is any callable policy(observation, driver) -> Decision. It sees a DriverObservation (never the Race
or a RaceCar) and the driver's fixed skill profile. The actions are proposals only: in P2-V2 none of them changes how
a car moves or whether a pass happens; the race decides that exactly as before. P2-V3 connects them to the car.
Separate from the strategist's interface in rl/policies.py, which makes pit calls.
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, NamedTuple

from abstract_classes import TyreCompound
from drivers import Driver
from race_control import Flag
from traffic import is_straight, time_factor

ATTACK_SKILL_SPAN = 1.0  # m/s less closing speed needed to attack per unit of attack skill above 0.5, placeholder
DEFENCE_SKILL_SPAN = 0.5  # s wider defending window per unit of defence skill above 0.5, placeholder
TYRE_SKILL_SPAN = 0.2  # tyre wear earlier conserving starts per unit of tyre_management above 0.5, placeholder


class DriverAction(Enum):
    MAINTAIN_PACE = "maintain pace"  # drive as the race model does: the default
    ATTACK = "attack"  # try to pass the car ahead
    DEFEND = "defend"  # protect the position from the car behind
    CONSERVE_TYRES = "conserve tyres"  # give up some pace to save tyre wear


@dataclass(frozen=True)
class DriverObservation:
    """What a driver may use on track, in physical units. None = no such car. Built by observe(); validated here."""
    laps_remaining: int  # full laps left after the current one (0 on the last lap)
    speed: float  # m/s now: own lap profile at this spot, with this car's time factor
    on_straight: bool  # in a straight segment: the only place the race allows a pass to start
    gap_ahead: float | None  # s this car needs to reach the car ahead (Race.interval)
    closing_speed: float | None  # m/s own speed minus the car ahead's speed, both at this spot; > 0 = closing
    gap_behind: float | None  # s the car behind needs to reach this car
    compound: TyreCompound
    tyre_wear: float  # 0 = new, 1 = fully worn
    wetness: float  # track wetness, 0 = dry, 1 = fully wet
    flag: Flag  # race-control flag (GREEN when the race has no race control)
    overtaking_allowed: bool  # race control allows passing here now
    drs: bool  # DRS usable on this lap

    def __post_init__(self):
        def number(value, low=0.0, high=math.inf):
            """A finite int or float (not a bool) from low to high."""
            return (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
                    and low <= value <= high)

        checks = {
            "laps_remaining must be an integer >= 0": isinstance(self.laps_remaining, int)
            and not isinstance(self.laps_remaining, bool) and self.laps_remaining >= 0,
            "speed must be a finite number >= 0": number(self.speed),
            "gap_ahead must be None or a finite number >= 0": self.gap_ahead is None or number(self.gap_ahead),
            "gap_behind must be None or a finite number >= 0": self.gap_behind is None or number(self.gap_behind),
            "closing_speed must be a finite number when gap_ahead is given, else None":
                self.closing_speed is None if self.gap_ahead is None else number(self.closing_speed, -math.inf),
            "compound must be a TyreCompound": isinstance(self.compound, TyreCompound),
            "tyre_wear must be a number from 0 to 1": number(self.tyre_wear, 0, 1),
            "wetness must be a number from 0 to 1": number(self.wetness, 0, 1),
            "flag must be a Flag": isinstance(self.flag, Flag),
            "on_straight, overtaking_allowed and drs must be bools":
                all(isinstance(value, bool) for value in (self.on_straight, self.overtaking_allowed, self.drs)),
        }
        problems = [message for message, ok in checks.items() if not ok]
        if problems:
            raise ValueError("; ".join(problems))


class Decision(NamedTuple):
    action: DriverAction
    reason: str  # short machine-readable code, e.g. "close_and_faster"
    features: dict  # the observation values and thresholds the rule compared, for the log


DriverPolicy = Callable[[DriverObservation, Driver], Decision]


class DecisionRecord(NamedTuple):
    """One logged decision: written when a car's action changes, not every step."""
    time: float  # s of race time when the decision was made (before the step)
    car: int
    lap: int  # the lap the car is on
    action: DriverAction
    reason: str
    features: dict


def available_actions(observation: DriverObservation) -> frozenset[DriverAction]:
    """Attack needs a car ahead, defend a car behind, and both need passing to be allowed."""
    actions = {DriverAction.MAINTAIN_PACE, DriverAction.CONSERVE_TYRES}
    if observation.overtaking_allowed and observation.gap_ahead is not None:
        actions.add(DriverAction.ATTACK)
    if observation.overtaking_allowed and observation.gap_behind is not None:
        actions.add(DriverAction.DEFEND)
    return frozenset(actions)


def decide(policy: DriverPolicy, observation: DriverObservation, driver: Driver) -> Decision:
    """Call a policy and reject anything that is not an available action."""
    decision = policy(observation, driver)
    if not isinstance(decision, Decision) or not isinstance(decision.action, DriverAction):
        raise ValueError(f"a driving policy must return a Decision with a DriverAction, got {decision!r}")
    if decision.action not in available_actions(observation):
        raise ValueError(f"{decision.action.name} is not available now (reason given: {decision.reason!r})")
    return decision


# ---- building an observation from the race -----------------------------------------------------------------------
# ponytail: reads Race's private helpers (_segment, _profiles, _in_zone, _drs_allowed, _overtaking_allowed) instead of
# widening Race's public API; give Race public accessors if a second module needs them.

def _factor(race, car) -> float:
    """The time factor Race._drive applies to this car now: pace, dirty air, DRS, then race control."""
    ahead = race.car_ahead(car)
    if race.traffic is None:
        factor = car.driver.time_factor()
    else:
        interval = race.interval(car, ahead) if ahead else math.inf
        factor = time_factor(race.traffic, car.driver, race._segment(car), interval, car.drs and race._drs_allowed())
    if race.race_control:
        factor = race.race_control.pace_factor(factor, race._in_zone(car), ahead is None)
    return factor


def _speed(race, car, distance: float) -> float:
    return race._profiles[car.number].speed_at(distance) / _factor(race, car)


def observe(race, car) -> DriverObservation:
    """The observation of one car on track (not finished, retired or in the pits)."""
    if not race._on_track(car):
        raise ValueError(f"car #{car.number} is not on track")
    ahead = race.car_ahead(car)
    behind = next((other for other in race.cars if other is not car and race._on_track(other)
                   and race.car_ahead(other) is car), None)
    speed = _speed(race, car, car.distance)
    rc = race.race_control
    return DriverObservation(
        laps_remaining=race.laps - car.laps - 1,
        speed=speed,
        on_straight=is_straight(race._segment(car)),
        gap_ahead=race.interval(car, ahead) if ahead else None,
        closing_speed=speed - _speed(race, ahead, car.distance) if ahead else None,
        gap_behind=race.interval(behind, car) if behind else None,
        compound=car.tyres.compound,
        tyre_wear=car.tyres.wear(race.compounds),
        wetness=race.weather.wetness if race.weather else 0.0,
        flag=rc.flag if rc else Flag.GREEN,
        overtaking_allowed=race._overtaking_allowed(car),
        drs=car.drs and race._drs_allowed(),
    )


def run(race, policies: dict[int, DriverPolicy], dt: float = 0.1) -> list[DecisionRecord]:
    """Run the race to the finish. Before every step each car with a policy decides; changes of action are logged.

    The decisions do not affect the race in P2-V2: the finish times are the same as race.run(dt)."""
    numbers = {car.number for car in race.cars}
    if not set(policies) <= numbers:
        raise ValueError(f"no car numbered {sorted(set(policies) - numbers)} in this race")
    log: list[DecisionRecord] = []
    last: dict[int, DriverAction] = {}
    while not race.finished:
        for car in race.cars:
            if car.number in policies and race._on_track(car):
                decision = decide(policies[car.number], observe(race, car), car.driver)
                if last.get(car.number) is not decision.action:
                    log.append(DecisionRecord(race.time, car.number, car.laps + 1, *decision))
                    last[car.number] = decision.action
        race.step(dt)
    return log


# ---- rule-based baselines ------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleBasedDriver:
    """Checks, in order: attack, defend, conserve tyres; otherwise maintain pace. Thresholds are for a 0.5 skill;
    the driver's attack, defence and tyre_management skills shift them (see the *_SKILL_SPAN constants)."""
    name: str
    attack_gap: float  # s, consider attacking only this close to the car ahead
    attack_margin: float  # m/s closing speed above which to attack
    defend_gap: float  # s, defend when the car behind is this close
    conserve_wear: float | None  # conserve tyres from this wear when not fighting; None = never

    def __post_init__(self):
        if not all(value >= 0 for value in (self.attack_gap, self.attack_margin, self.defend_gap)):
            raise ValueError("attack_gap, attack_margin and defend_gap must be >= 0")
        if self.conserve_wear is not None and not 0 <= self.conserve_wear <= 1:
            raise ValueError("conserve_wear must be None or 0-1")

    def __call__(self, observation: DriverObservation, driver: Driver) -> Decision:
        available = available_actions(observation)
        if DriverAction.ATTACK in available and observation.gap_ahead <= self.attack_gap:
            needed = max(0.0, self.attack_margin - ATTACK_SKILL_SPAN * (driver.attack - 0.5))  # never when not faster
            if observation.closing_speed > needed:
                return Decision(DriverAction.ATTACK, "close_and_faster", {
                    "gap_ahead": observation.gap_ahead, "closing_speed": observation.closing_speed, "needed": needed})
        if DriverAction.DEFEND in available:
            window = max(0.0, self.defend_gap + DEFENCE_SKILL_SPAN * (driver.defence - 0.5))
            if observation.gap_behind <= window:
                return Decision(DriverAction.DEFEND, "car_behind_close",
                                {"gap_behind": observation.gap_behind, "window": window})
        if self.conserve_wear is not None and observation.laps_remaining > 0:
            start = self.conserve_wear - TYRE_SKILL_SPAN * (driver.tyre_management - 0.5)
            if observation.tyre_wear >= start:
                return Decision(DriverAction.CONSERVE_TYRES, "tyres_worn",
                                {"tyre_wear": observation.tyre_wear, "conserve_from": start})
        return Decision(DriverAction.MAINTAIN_PACE, "no_trigger", {})


# Placeholder thresholds chosen to order the three styles, not fitted to anything.
CONSERVATIVE = RuleBasedDriver("conservative", attack_gap=0.5, attack_margin=2.0, defend_gap=0.3, conserve_wear=0.3)
BALANCED = RuleBasedDriver("balanced", attack_gap=1.0, attack_margin=1.0, defend_gap=0.6, conserve_wear=0.6)
AGGRESSIVE = RuleBasedDriver("aggressive", attack_gap=1.5, attack_margin=0.3, defend_gap=1.0, conserve_wear=None)
BASELINES = (CONSERVATIVE, BALANCED, AGGRESSIVE)
