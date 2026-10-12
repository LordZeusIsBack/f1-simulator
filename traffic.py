import math
from dataclasses import dataclass

from abstract_classes import TrackSegment
from drivers import Driver


@dataclass(frozen=True)
class TrafficRules:
    """Thresholds and effects of the car-to-car model. Every value is a model assumption, not F1 data."""
    min_gap: float = 5.0  # m, closest a car follows before it must pass or be held behind
    dirty_air_interval: float = 1.0  # s, following closer than this costs pace in corners
    dirty_air_loss: float = 0.02  # extra time fraction in corners while in dirty air
    drs_interval: float = 1.0  # s, being closer than this at the line enables DRS for the next lap
    drs_from_lap: int = 3  # first lap on which DRS can be used
    drs_min_straight: float = 500.0  # m, straights at least this long are DRS zones
    drs_gain: float = 0.035  # time fraction saved in a DRS zone (≈ 3.6 % more speed)
    overtake_margin: float = 2.0  # m/s speed advantage needed to pass, between equal racecraft
    racecraft_effect: float = 1.0  # m/s the margin changes per unit of racecraft difference


def is_straight(segment: TrackSegment) -> bool:
    return segment.radius == math.inf


def is_drs_zone(rules: TrafficRules, segment: TrackSegment) -> bool:
    return is_straight(segment) and segment.length >= rules.drs_min_straight


def time_factor(rules: TrafficRules, driver: Driver, segment: TrackSegment, interval: float, drs: bool) -> float:
    """Multiplier on the car's profile time at this spot: >1 slower, <1 faster."""
    factor = driver.time_factor()
    if not is_straight(segment) and interval < rules.dirty_air_interval:
        factor *= 1 + rules.dirty_air_loss
    if drs and is_drs_zone(rules, segment):
        factor *= 1 - rules.drs_gain
    return factor


def drs_enabled(rules: TrafficRules, lap: int, interval: float) -> bool:
    """Decided as a car starts `lap`: within drs_interval of the car ahead, from drs_from_lap on."""
    return lap >= rules.drs_from_lap and interval < rules.drs_interval


def required_advantage(rules: TrafficRules, attacker: Driver, defender: Driver) -> float:
    """m/s an attacker must be faster by; better racecraft than the defender lowers it."""
    return rules.overtake_margin - rules.racecraft_effect * (attacker.racecraft - defender.racecraft)


def can_attack(rules: TrafficRules, segment: TrackSegment, advantage: float, attacker: Driver, defender: Driver) -> bool:
    """A pass may start only on a straight, with enough speed advantage over the car ahead."""
    return is_straight(segment) and advantage >= required_advantage(rules, attacker, defender)
