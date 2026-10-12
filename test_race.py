import math
from unittest import TestCase

from abstract_classes import Car, CarSpecification, TyreCompound
from cars import CARS
from physics import TYRE_GRIP
from race import GRID_SPACING, LapProfile, Race, RaceCar
from simulation import simulate_lap
from test_simulation import Stadium
from tracks import Monza
from tyres import Compound

assert_raises = TestCase().assertRaises
FAST = Car(CarSpecification(power=750_000, drag=1.2, downforce=3.5))
SLOW = Car(CarSpecification(power=500_000, drag=1.2, downforce=3.5))
V1_TYRES = {TyreCompound.MEDIUM: Compound(TYRE_GRIP, wear_per_lap=0.0)}


def v1_race(track, laps, grid):
    """V1 behaviour: no fuel burn, no tyre wear, no traffic."""
    return Race(track, laps, grid, fuel_per_lap=0.0, compounds=V1_TYRES, traffic=None)


def lap_time(car):
    return simulate_lap(car, Stadium())[0]


def test_v1_monza_race_results_unchanged():
    # recorded from V1 (commit 3fbf350): 53 laps, 8 cars, two per team in CARS order
    v1 = {1: 5011.391854138659, 2: 5011.534385461075, 3: 5045.687502825008, 4: 5045.833538683694,
          5: 4982.460995837225, 6: 4982.598205595793, 7: 5051.314782433612, 8: 5051.46414224547}
    entries = [(team, car) for team, car in CARS.items() for _ in range(2)]
    grid = [RaceCar(number, team, car) for number, (team, car) in enumerate(entries, start=1)]
    v1_race(Monza(), 53, grid).run(0.5)
    for car in grid:
        assert math.isclose(car.finish_time, v1[car.number], abs_tol=1e-6)


def test_grid_puts_cars_behind_the_line_in_given_order():
    grid = [RaceCar(44, "A", FAST), RaceCar(1, "B", FAST), RaceCar(16, "C", FAST)]
    race = v1_race(Stadium(), 3, grid)
    assert [car.distance for car in grid] == [0.0, -GRID_SPACING, -2 * GRID_SPACING]
    assert race.time == 0.0 and not race.finished
    assert race.standings() == grid
    assert [race.laps_completed(car) for car in grid] == [0, 0, 0]


def test_team_mates_share_the_car_but_not_the_race_state():
    first, second = RaceCar(1, "Team", FAST), RaceCar(2, "Team", FAST)
    race = v1_race(Stadium(), 2, [first, second])
    for _ in range(20):
        race.step(0.5)
    assert first.car is second.car
    assert first.distance > second.distance > 0
    before = second.distance
    first.distance += 100
    assert second.distance == before


def test_positions_follow_progress_not_grid_order():
    slow, fast = RaceCar(1, "Slow", SLOW), RaceCar(2, "Fast", FAST)
    race = v1_race(Stadium(), 5, [slow, fast])
    assert race.standings() == [slow, fast]
    race.run(0.5)
    assert race.standings() == [fast, slow]
    assert fast.finish_time < slow.finish_time


def test_running_cars_are_ordered_by_distance_and_finished_cars_lead():
    a, b, c = RaceCar(1, "A", FAST), RaceCar(2, "B", FAST), RaceCar(3, "C", FAST)
    race = v1_race(Stadium(), 1, [a, b, c])
    a.distance, b.distance, c.distance = 100.0, 300.0, 200.0
    assert race.standings() == [b, c, a]
    a.distance, a.finish_time = race.race_distance, 50.0
    assert race.standings() == [a, b, c]


def test_single_car_race_lasts_laps_times_the_v0_lap_time():
    car = RaceCar(1, "Solo", FAST)
    race = v1_race(Stadium(), 3, [car])
    assert race.run(0.5) == [car]
    assert race.finished and race.laps_completed(car) == 3
    assert car.distance == race.race_distance
    assert math.isclose(car.finish_time, 3 * lap_time(FAST), rel_tol=1e-9)


def test_lap_is_counted_when_the_car_crosses_the_line():
    car = RaceCar(1, "Solo", FAST)
    race = v1_race(Stadium(), 2, [car])
    race.step(lap_time(FAST) - 0.01)
    assert race.laps_completed(car) == 0
    race.step(0.02)
    assert race.laps_completed(car) == 1 and not race.finished


def test_race_ends_only_when_every_car_has_completed_all_laps():
    grid = [RaceCar(1, "Fast", FAST), RaceCar(2, "Slow", SLOW)]
    race = v1_race(Stadium(), 2, grid)
    while grid[0].finish_time is None:
        race.step(0.5)
    assert not race.finished and race.laps_completed(grid[1]) < 2
    race.run(0.5)
    assert all(race.laps_completed(car) == 2 for car in grid)
    assert race.time >= max(car.finish_time for car in grid)


def test_results_do_not_depend_on_step_size():
    def finish_times(dt):
        grid = [RaceCar(1, "Fast", FAST), RaceCar(2, "Slow", SLOW), RaceCar(3, "Fast", FAST)]
        return [car.finish_time for car in v1_race(Stadium(), 4, grid).run(dt)]

    for coarse, fine in zip(finish_times(3.0), finish_times(0.05)):
        assert math.isclose(coarse, fine, abs_tol=1e-6)


def test_same_inputs_give_identical_results():
    def result():
        grid = [RaceCar(1, "Fast", FAST), RaceCar(2, "Slow", SLOW)]
        return [(car.number, car.finish_time) for car in v1_race(Stadium(), 3, grid).run(0.5)]

    assert result() == result()


def test_lap_profile_reproduces_the_v0_lap_and_inverts():
    profile = LapProfile(FAST, Stadium())
    assert math.isclose(profile.time[-1], lap_time(FAST), rel_tol=1e-12)
    assert math.isclose(profile.distance[-1], Stadium().length, rel_tol=1e-12)
    for distance in (-16.0, 0.0, 123.4, 1314.0, 5000.0):
        assert math.isclose(profile.distance_at(profile.time_at(distance)), distance, abs_tol=1e-9)


def test_invalid_race_configuration_is_rejected():
    for laps in (0, -1, 2.5, "3"):
        with assert_raises(ValueError):
            v1_race(Stadium(), laps, [RaceCar(1, "A", FAST)])
    with assert_raises(ValueError):
        v1_race(Stadium(), 3, [])
    with assert_raises(ValueError):
        v1_race(Stadium(), 3, [RaceCar(1, "A", FAST), RaceCar(1, "B", FAST)])
    race = v1_race(Stadium(), 3, [RaceCar(1, "A", FAST)])
    for dt in (0, -0.5):
        with assert_raises(ValueError):
            race.step(dt)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
