"""P2-V2: driver observations, actions, the policy interface, the rule-based baselines and the decision log.
The actions are proposals only in P2-V2, so no test here expects them to change a race (one checks that they don't)."""
import math
from dataclasses import replace
from unittest import TestCase

from abstract_classes import TyreCompound
from drivers import Driver
from driving import (AGGRESSIVE, BALANCED, BASELINES, CONSERVATIVE, Decision, DecisionRecord, DriverAction,
                     DriverObservation, RuleBasedDriver, available_actions, decide, observe, run)
from race import Race, RaceCar
from race_control import Flag, Incident, RaceControl
from strategy import PitStop, Strategy
from test_race import FAST, SLOW
from test_simulation import Stadium
from weather import Weather, WeatherPoint

assert_raises = TestCase().assertRaises
A = DriverAction
CLEAR = DriverObservation(laps_remaining=5, speed=60.0, on_straight=True, gap_ahead=None, closing_speed=None,
                          gap_behind=None, compound=TyreCompound.MEDIUM, tyre_wear=0.1, wetness=0.0, flag=Flag.GREEN,
                          overtaking_allowed=True, drs=False)


def scene(**changes) -> DriverObservation:
    return replace(CLEAR, **changes)


def actions(observation, driver=Driver()):
    """What conservative, balanced and aggressive choose, in that order."""
    return [policy(observation, driver).action for policy in BASELINES]


def three_car_grid():
    return [RaceCar(1, "A", SLOW), RaceCar(2, "B", FAST, driver=Driver(attack=0.9)), RaceCar(3, "C", FAST)]


# ---- observation -------------------------------------------------------------------------------------------------

def test_observation_rejects_invalid_and_inconsistent_values():
    bad = {
        "laps_remaining": (-1, 1.0, True), "speed": (-0.1, math.inf, math.nan, "60"),
        "gap_ahead": (-0.1, math.inf), "gap_behind": (-0.1, math.nan, "0.5"),
        "tyre_wear": (-0.01, 1.01, None, False), "wetness": (1.5, math.nan),
        "compound": ("medium",), "flag": (0,), "on_straight": (1,), "overtaking_allowed": (None,), "drs": ("no",),
    }
    for field, values in bad.items():
        for value in values:
            with assert_raises(ValueError) as caught:
                scene(**{field: value})
            assert field in str(caught.exception)
    with assert_raises(ValueError):
        scene(closing_speed=1.0)  # a closing speed with no car ahead
    with assert_raises(ValueError):
        scene(gap_ahead=0.5)  # a car ahead with no closing speed
    with assert_raises(ValueError):
        scene(gap_ahead=0.5, closing_speed=math.inf)
    assert scene(gap_ahead=0.5, closing_speed=-2.0).closing_speed == -2.0  # being dropped is valid


def test_observe_reads_gaps_tyres_and_segment_from_a_race():
    race = Race(Stadium(), 4, three_car_grid())
    for _ in range(300):
        race.step(0.1)
    order = [car for car in race.standings() if race._on_track(car)]
    first, middle, last = (observe(race, car) for car in order)
    assert first.gap_ahead is None and first.closing_speed is None and first.gap_behind is not None
    assert last.gap_behind is None and last.gap_ahead is not None
    assert middle.gap_ahead == race.interval(order[1], order[0]) and middle.gap_behind == race.interval(order[2], order[1])
    for car, seen in zip(order, (first, middle, last)):
        assert seen.laps_remaining == 4 - car.laps - 1 and seen.compound is TyreCompound.MEDIUM
        assert seen.tyre_wear == car.tyres.wear(race.compounds) and seen.speed > 0
        assert seen.on_straight == (race._segment(car).radius == math.inf)
        assert (seen.flag, seen.overtaking_allowed, seen.wetness) == (Flag.GREEN, True, 0.0)


def test_missing_data_alone_on_a_dry_track_without_race_control():
    car = RaceCar(1, "Solo", FAST)
    race = Race(Stadium(), 3, [car], traffic=None)
    race.step(1.0)
    seen = observe(race, car)
    assert (seen.gap_ahead, seen.closing_speed, seen.gap_behind) == (None, None, None)
    assert (seen.flag, seen.wetness, seen.drs) == (Flag.GREEN, 0.0, False)
    assert available_actions(seen) == {A.MAINTAIN_PACE, A.CONSERVE_TYRES}


def test_weather_and_flags_reach_the_observation():
    weather = Weather([WeatherPoint(0, 20.0), WeatherPoint(1, 20.0, 10.0)])
    control = RaceControl([Incident(5.0, Flag.VSC, 60.0)])
    race = Race(Stadium(), 4, three_car_grid(), weather=weather, race_control=control)
    for _ in range(100):
        race.step(0.1)
    seen = observe(race, race.cars[1])
    assert seen.flag is Flag.VSC and not seen.overtaking_allowed and seen.wetness > 0
    assert available_actions(seen) == {A.MAINTAIN_PACE, A.CONSERVE_TYRES}  # no attacking or defending under VSC
    assert {policy(seen, Driver(attack=1.0, defence=1.0)).action for policy in BASELINES} <= available_actions(seen)


def test_observe_refuses_a_car_that_is_not_on_track():
    leader = RaceCar(1, "A", FAST, Strategy(TyreCompound.MEDIUM, 10.0, (PitStop(1, TyreCompound.HARD),)))
    race = Race(Stadium(), 3, [leader, RaceCar(2, "B", FAST)])
    while not leader.pit_exit > race.time:
        race.step(0.1)
    with assert_raises(ValueError):
        observe(race, leader)


# ---- interface ---------------------------------------------------------------------------------------------------

def test_decide_accepts_only_available_driver_actions():
    assert decide(BALANCED, CLEAR, Driver()) == Decision(A.MAINTAIN_PACE, "no_trigger", {})
    for broken in (lambda o, d: "attack", lambda o, d: A.ATTACK, lambda o, d: Decision("attack", "", {})):
        with assert_raises(ValueError):
            decide(broken, CLEAR, Driver())
    with assert_raises(ValueError) as caught:
        decide(lambda o, d: Decision(A.ATTACK, "always", {}), CLEAR, Driver())  # nobody ahead
    assert "ATTACK is not available" in str(caught.exception)
    assert available_actions(scene(gap_ahead=0.3, closing_speed=1.0, gap_behind=0.3)) == set(A)
    assert available_actions(scene(gap_ahead=0.3, closing_speed=1.0, overtaking_allowed=False)) == {
        A.MAINTAIN_PACE, A.CONSERVE_TYRES}


def test_rule_based_driver_thresholds_are_validated():
    for bad in ({"attack_gap": -1.0}, {"attack_margin": -0.1}, {"defend_gap": -0.5}, {"conserve_wear": 1.5}):
        with assert_raises(ValueError):
            replace(BALANCED, **bad)
    assert replace(BALANCED, conserve_wear=None).conserve_wear is None


def test_decisions_are_deterministic():
    seen = scene(gap_ahead=0.8, closing_speed=1.2, gap_behind=0.4, tyre_wear=0.7)
    for policy in BASELINES:
        assert len({policy(seen, Driver(attack=0.3)).action for _ in range(5)}) == 1

    def replay():
        return run(Race(Stadium(), 4, three_car_grid()), {1: CONSERVATIVE, 2: BALANCED, 3: AGGRESSIVE})

    first = replay()
    assert first == replay() and first


# ---- the three baselines -----------------------------------------------------------------------------------------

def test_baselines_differ_on_when_to_attack():
    assert actions(scene(gap_ahead=0.8, closing_speed=1.5)) == [A.MAINTAIN_PACE, A.ATTACK, A.ATTACK]  # conservative: too far
    assert actions(scene(gap_ahead=0.4, closing_speed=1.5)) == [A.MAINTAIN_PACE, A.ATTACK, A.ATTACK]  # needs 2.0 m/s
    assert actions(scene(gap_ahead=0.4, closing_speed=2.5)) == [A.ATTACK, A.ATTACK, A.ATTACK]
    assert actions(scene(gap_ahead=0.4, closing_speed=0.5)) == [A.MAINTAIN_PACE, A.MAINTAIN_PACE, A.ATTACK]
    assert actions(scene(gap_ahead=1.3, closing_speed=3.0)) == [A.MAINTAIN_PACE, A.MAINTAIN_PACE, A.ATTACK]


def test_baselines_differ_on_when_to_defend_and_attack_comes_first():
    assert actions(scene(gap_behind=0.25)) == [A.DEFEND, A.DEFEND, A.DEFEND]
    assert actions(scene(gap_behind=0.5)) == [A.MAINTAIN_PACE, A.DEFEND, A.DEFEND]
    assert actions(scene(gap_behind=0.9)) == [A.MAINTAIN_PACE, A.MAINTAIN_PACE, A.DEFEND]
    assert actions(scene(gap_ahead=0.4, closing_speed=2.5, gap_behind=0.1)) == [A.ATTACK] * 3


def test_baselines_differ_on_tyre_conservation():
    assert actions(scene(tyre_wear=0.4)) == [A.CONSERVE_TYRES, A.MAINTAIN_PACE, A.MAINTAIN_PACE]
    assert actions(scene(tyre_wear=0.7)) == [A.CONSERVE_TYRES, A.CONSERVE_TYRES, A.MAINTAIN_PACE]  # aggressive: never
    assert actions(scene(tyre_wear=0.7, laps_remaining=0)) == [A.MAINTAIN_PACE] * 3  # nothing to save on the last lap
    assert actions(scene(tyre_wear=0.7, gap_behind=0.2)) == [A.DEFEND] * 3  # fighting comes before saving tyres


# ---- skills shift the thresholds ---------------------------------------------------------------------------------

def test_attack_skill_lowers_the_closing_speed_needed():
    seen = scene(gap_ahead=0.5, closing_speed=0.8)
    assert BALANCED(seen, Driver(attack=0.5)).action is A.MAINTAIN_PACE  # needs 1.0 m/s
    decision = BALANCED(seen, Driver(attack=1.0))
    assert decision.action is A.ATTACK and math.isclose(decision.features["needed"], 0.5)
    assert math.isclose(BALANCED(scene(gap_ahead=0.5, closing_speed=1.6), Driver(attack=0.0)).features["needed"], 1.5)
    assert BALANCED(scene(gap_ahead=0.5, closing_speed=1.4), Driver(attack=0.0)).action is A.MAINTAIN_PACE


def test_top_attack_skill_still_needs_to_be_faster():
    best = Driver(attack=1.0)
    for closing in (0.0, -1.0):
        assert {policy(scene(gap_ahead=0.2, closing_speed=closing), best).action for policy in BASELINES} == {
            A.MAINTAIN_PACE}


def test_defence_skill_widens_the_defending_window():
    seen = scene(gap_behind=0.75)
    assert BALANCED(seen, Driver(defence=0.5)).action is A.MAINTAIN_PACE  # window 0.6 s
    decision = BALANCED(seen, Driver(defence=1.0))
    assert decision.action is A.DEFEND and math.isclose(decision.features["window"], 0.85)
    weak = Driver(defence=0.0)  # conservative window 0.3 - 0.25 = 0.05 s
    assert CONSERVATIVE(scene(gap_behind=0.1), weak).action is A.MAINTAIN_PACE
    assert math.isclose(CONSERVATIVE(scene(gap_behind=0.04), weak).features["window"], 0.05)


def test_tyre_management_skill_starts_conserving_earlier():
    seen = scene(tyre_wear=0.55)
    assert BALANCED(seen, Driver(tyre_management=0.5)).action is A.MAINTAIN_PACE  # from 0.6
    decision = BALANCED(seen, Driver(tyre_management=1.0))
    assert decision.action is A.CONSERVE_TYRES and math.isclose(decision.features["conserve_from"], 0.5)
    assert AGGRESSIVE(scene(tyre_wear=1.0), Driver(tyre_management=1.0)).action is A.MAINTAIN_PACE


# ---- the decision log ----------------------------------------------------------------------------------------------

def test_run_logs_changes_of_action_with_reasons_and_does_not_change_the_race():
    policies = {1: CONSERVATIVE, 2: BALANCED, 3: AGGRESSIVE}
    race = Race(Stadium(), 4, three_car_grid())
    log = run(race, policies)
    plain = Race(Stadium(), 4, three_car_grid())
    plain.run(0.1)
    assert [car.finish_time for car in race.cars] == [car.finish_time for car in plain.cars]  # proposals only
    assert race.overtakes == plain.overtakes
    assert {record.car for record in log} == {1, 2, 3} and all(isinstance(r, DecisionRecord) for r in log)
    for number in policies:
        mine = [record for record in log if record.car == number]
        assert all(a.action is not b.action for a, b in zip(mine, mine[1:]))  # logged only when it changes
    reasons = {A.ATTACK: "close_and_faster", A.DEFEND: "car_behind_close", A.CONSERVE_TYRES: "tyres_worn",
               A.MAINTAIN_PACE: "no_trigger"}
    for record in log:
        assert record.reason == reasons[record.action] and 1 <= record.lap <= 4
        assert all(isinstance(value, float) for value in record.features.values())
    attack = next(record for record in log if record.action is A.ATTACK)
    assert set(attack.features) == {"gap_ahead", "closing_speed", "needed"}
    assert attack.features["closing_speed"] > attack.features["needed"]


def test_run_rejects_policies_for_cars_not_in_the_race():
    with assert_raises(ValueError):
        run(Race(Stadium(), 2, three_car_grid()), {9: BALANCED})


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
