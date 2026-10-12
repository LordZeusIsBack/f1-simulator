import math
from unittest import TestCase

from abstract_classes import Corner, Straight, TyreCompound
from drivers import Driver
from race import Race, RaceCar
from strategy import PitStop, Strategy
from test_race import FAST, SLOW, V1_TYRES, lap_time
from test_simulation import Stadium
from traffic import TrafficRules, can_attack, drs_enabled, required_advantage, time_factor
from tyres import Compound

assert_raises = TestCase().assertRaises
RULES = TrafficRules()
NO_DRS = TrafficRules(drs_from_lap=99)
CORNER, STRAIGHT, SHORT_STRAIGHT = Corner(100, 50, 0), Straight(600, math.inf, 0), Straight(400, math.inf, 0)


def run(grid, laps=4, rules=RULES, dt=0.1, **settings):
    """Run a race to the finish, recording standings and gaps after every step."""
    race = Race(Stadium(), laps, grid, traffic=rules, **settings)
    history = []
    while not race.finished:
        race.step(dt)
        history.append(([car.number for car in race.standings()], {car.number: car.distance for car in grid}))
    return race, history


def passes(race):
    return [(event.attacker, event.defender) for event in race.overtakes if event.outcome == "passed"]


def test_driver_attributes_are_validated():
    assert Driver().time_factor() == 1.0 and Driver().racecraft == 0.5
    assert math.isclose(Driver(pace=0.0).time_factor(), 1.01)
    assert Driver("A", pace=0.5, racecraft=1).pace == 0.5
    for bad in (-0.1, 1.1, "fast", None, True, math.nan):
        with assert_raises(ValueError):
            Driver(pace=bad)
        with assert_raises(ValueError):
            Driver(racecraft=bad)



def test_driver_pace_stretches_lap_time_with_or_without_traffic():
    for rules in (None, RULES):
        car = RaceCar(1, "Solo", FAST, driver=Driver(pace=0.0))
        Race(Stadium(), 3, [car], fuel_per_lap=0.0, compounds=V1_TYRES, traffic=rules).run(0.5)
        assert math.isclose(car.finish_time, 3 * lap_time(FAST) * 1.01, rel_tol=1e-9)


def test_car_ahead_is_the_nearest_car_on_track():
    a, b, c = RaceCar(1, "A", FAST), RaceCar(2, "B", FAST), RaceCar(3, "C", FAST)
    race = Race(Stadium(), 4, [a, b, c])
    assert race.car_ahead(a) is None and race.car_ahead(b) is a and race.car_ahead(c) is b
    b.pit_exit = race.time + 10  # b is in the pits: c now follows a
    assert race.car_ahead(c) is a
    a.finish_time = 1.0  # a has finished: nobody is ahead of c on track
    assert race.car_ahead(c) is None


def test_interval_is_the_followers_time_to_the_car_ahead():
    a, b = RaceCar(1, "A", FAST), RaceCar(2, "B", FAST)
    race = Race(Stadium(), 4, [a, b])
    gap = race.interval(b, a)  # 8 m on the grid at the car's speed there
    assert math.isclose(gap, 8 / race._profiles[2].speed_at(-8), rel_tol=0.05)
    a.distance += Stadium().length  # one lap further ahead: one lap time more
    assert math.isclose(race.interval(b, a), gap + race._profiles[2].time[-1], rel_tol=1e-9)


def test_dirty_air_only_close_behind_and_only_in_corners():
    driver = Driver()
    assert math.isclose(time_factor(RULES, driver, CORNER, 0.99, False), 1.02)
    assert time_factor(RULES, driver, CORNER, 1.0, False) == 1.0
    assert time_factor(RULES, driver, CORNER, 5.0, False) == 1.0
    assert time_factor(RULES, driver, STRAIGHT, 0.2, False) == 1.0


def test_follower_loses_time_in_traffic_and_the_leader_does_not():
    def finish_times(rules):
        grid = [RaceCar(1, "A", FAST), RaceCar(2, "A", FAST)]
        race, _ = run(grid, laps=3, rules=rules)
        return grid[0].finish_time, grid[1].finish_time

    (lead_free, follow_free), (lead, follow) = finish_times(None), finish_times(NO_DRS)
    assert math.isclose(lead, lead_free, abs_tol=0.1)  # nobody ahead: no traffic
    assert follow - lead > follow_free - lead_free + 0.5  # dirty air pushes the follower back


def test_drs_thresholds():
    assert drs_enabled(RULES, 3, 0.999) and not drs_enabled(RULES, 3, 1.0) and not drs_enabled(RULES, 3, 1.5)
    assert not drs_enabled(RULES, 2, 0.1)  # not before drs_from_lap
    driver = Driver()
    assert math.isclose(time_factor(RULES, driver, STRAIGHT, 5.0, True), 1 - RULES.drs_gain)
    assert time_factor(RULES, driver, SHORT_STRAIGHT, 5.0, True) == 1.0  # shorter than a DRS zone
    assert time_factor(RULES, driver, CORNER, 5.0, True) == 1.0
    assert time_factor(RULES, driver, STRAIGHT, 5.0, False) == 1.0


def test_drs_follows_the_rule_at_every_line_crossing():
    leader = RaceCar(1, "A", FAST, Strategy(TyreCompound.MEDIUM, 7 * 1.9, (PitStop(4, TyreCompound.HARD),)))
    follower = RaceCar(2, "B", FAST)  # close behind until the leader pits after lap 4
    race = Race(Stadium(), 7, [leader, follower], traffic=RULES)
    seen = []
    while not race.finished:
        laps = {car.number: car.laps for car in race.cars}
        race.step(0.1)
        for car in race.cars:
            if car.laps > laps[car.number] and car.finish_time is None:
                ahead = race.car_ahead(car)
                expected = (car.pit_exit <= race.time and ahead is not None
                            and drs_enabled(RULES, car.laps + 1, race.interval(car, ahead)))
                assert car.drs == expected, (car.number, car.laps)
                seen.append((car.number, car.laps, expected))
    assert (2, 1, False) in seen  # starting lap 2: too early, DRS only from lap 3
    assert (2, 2, True) in seen and (2, 4, False) in seen  # on behind car 1, off once car 1 pits


def test_faster_car_passes_on_a_straight_and_positions_update():
    slow, fast = RaceCar(1, "Slow", SLOW), RaceCar(2, "Fast", FAST)
    race, history = run([slow, fast], laps=2, rules=NO_DRS)
    [event] = [e for e in race.overtakes if e.outcome == "passed"]
    assert (event.attacker, event.defender) == (2, 1) and event.advantage >= event.required
    assert history[0][0] == [1, 2] and history[-1][0] == [2, 1] and race.standings() == [fast, slow]


def test_small_advantage_is_held_up_without_drs_and_passes_with_it():
    def race_with(rules):
        grid = [RaceCar(1, "A", FAST, driver=Driver(pace=0.0)), RaceCar(2, "B", FAST, driver=Driver(pace=1.0))]
        return run(grid, laps=6, rules=rules)

    race, history = race_with(NO_DRS)
    assert passes(race) == [] and any(e.outcome == "held up" and e.attacker == 2 for e in race.overtakes)
    assert all(e.advantage < e.required for e in race.overtakes if e.outcome == "held up")
    for order, distance in history:  # never closer than min_gap while held behind a car still racing
        if order == [1, 2] and distance[1] < race.race_distance:
            assert distance[1] - distance[2] >= NO_DRS.min_gap - 1e-6
    race, _ = race_with(RULES)
    assert (2, 1) in passes(race)  # DRS gives the extra speed


def test_racecraft_decides_a_close_fight():
    assert required_advantage(RULES, Driver(racecraft=1), Driver(racecraft=0)) == 1.0
    assert required_advantage(RULES, Driver(racecraft=0), Driver(racecraft=1)) == 3.0
    assert required_advantage(RULES, Driver(), Driver()) == 2.0
    assert not can_attack(RULES, CORNER, 50.0, Driver(), Driver())  # never in a corner
    rules = TrafficRules(drs_from_lap=99, overtake_margin=0.6, racecraft_effect=0.5)

    def fight(attacker, defender):
        grid = [RaceCar(1, "A", FAST, driver=Driver(pace=0.0, racecraft=defender)),
                RaceCar(2, "B", FAST, driver=Driver(pace=1.0, racecraft=attacker))]
        return passes(run(grid, laps=6, rules=rules)[0])

    assert fight(attacker=1.0, defender=0.0) == [(2, 1)]
    assert fight(attacker=0.0, defender=1.0) == []


def test_passing_a_car_in_the_pits_is_not_an_overtake():
    leader = RaceCar(1, "A", FAST, Strategy(TyreCompound.MEDIUM, 10.0, (PitStop(1, TyreCompound.HARD),)))
    follower = RaceCar(2, "B", FAST)
    race, history = run([leader, follower], laps=3, rules=NO_DRS)
    [stop] = race.pit_events
    assert stop.number == 1
    assert passes(race) == []  # the follower went by while car 1 stood in the pits
    assert race.standings()[0] is follower and any(order == [2, 1] for order, _ in history)


def test_tyre_grip_feeds_the_overtaking_decision():
    compounds = {TyreCompound.SOFT: Compound(2.4, 0.0), TyreCompound.HARD: Compound(1.6, 0.0)}

    def attacker_on(compound):
        grid = [RaceCar(1, "A", FAST, Strategy(TyreCompound.HARD, 0.0)), RaceCar(2, "B", FAST, Strategy(compound, 0.0))]
        return passes(run(grid, laps=4, rules=NO_DRS, fuel_per_lap=0.0, compounds=compounds)[0])

    assert attacker_on(TyreCompound.SOFT) == [(2, 1)]
    assert attacker_on(TyreCompound.HARD) == []


def test_traffic_race_is_deterministic():
    def replay():
        grid = [RaceCar(1, "A", SLOW, driver=Driver(racecraft=0.2)), RaceCar(2, "B", FAST),
                RaceCar(3, "C", FAST, Strategy(TyreCompound.SOFT, 6 * 1.9, (PitStop(3, TyreCompound.MEDIUM),)),
                        Driver(pace=0.6))]
        race, _ = run(grid, laps=6)
        return [car.finish_time for car in grid], race.overtakes, race.pit_events

    first = replay()
    assert first == replay() and first[1]  # identical, and something happened



def test_v3_race_results_unchanged_without_weather():
    # recorded from V3 (commit 9fb0290): three cars, traffic on, one pit stop
    grid = [RaceCar(1, "A", SLOW, driver=Driver(racecraft=0.2)), RaceCar(2, "B", FAST),
            RaceCar(3, "C", FAST, Strategy(TyreCompound.SOFT, 6 * 1.9, (PitStop(3, TyreCompound.MEDIUM),)), Driver(pace=0.6))]
    race = Race(Stadium(), 6, grid)
    race.run(0.1)
    v3 = {1: 153.14997972804318, 2: 144.53210636577248, 3: 166.7806183551926}
    assert all(math.isclose(car.finish_time, v3[car.number], abs_tol=1e-6) for car in grid)
    assert [(e.attacker, e.defender, e.outcome, round(e.time, 1)) for e in race.overtakes] == [
        (2, 1, "passed", 2.8), (1, 2, "held up", 2.9), (3, 1, "passed", 4.4), (1, 3, "held up", 4.5), (3, 2, "aborted", 72.5)]


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
