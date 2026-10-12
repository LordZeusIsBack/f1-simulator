import math
from unittest import TestCase

from abstract_classes import TyreCompound
from physics import TYRE_GRIP
from race import FUEL_CAPACITY, REFUEL_RATE, LapProfile, Race, RaceCar
from strategy import PitStop, Strategy
from test_race import FAST, SLOW, V1_TYRES, lap_time
from test_simulation import Stadium
from tyres import COMPOUNDS, DRY_COMPOUNDS, WORN_GRIP_LOSS, Compound, Tyres

assert_raises = TestCase().assertRaises
SOFT, MEDIUM, HARD = TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD
LENGTH = Stadium().length


def solo(strategy, laps=4, **settings):
    """A one-car race on the test track, run to the finish."""
    car = RaceCar(1, "Solo", FAST, strategy)
    race = Race(Stadium(), laps, [car], **settings)
    race.run(0.5)
    return car, race


def test_dry_compounds_start_new_and_wet_ones_are_rejected():
    for compound in (SOFT, MEDIUM, HARD):
        tyres = Tyres(compound)
        assert tyres.laps == 0 and tyres.wear() == 0.0
        assert tyres.grip() == COMPOUNDS[compound].grip
        car, _ = solo(Strategy(compound, 4 * 1.9))
        assert car.tyres.compound is compound and car.tyres.laps == 4
    assert COMPOUNDS[MEDIUM].grip == TYRE_GRIP  # new mediums are V0's tyre
    for compound in (TyreCompound.INTERMEDIATE, TyreCompound.WET, "soft"):  # not in V2's dry-only table
        with assert_raises(ValueError):
            Race(Stadium(), 4, [RaceCar(1, "A", FAST, Strategy(compound, 10.0))], compounds=DRY_COMPOUNDS)


def test_wear_grows_per_lap_and_costs_grip_and_lap_time():
    rate = COMPOUNDS[SOFT].wear_per_lap
    for laps in (0, 1, 5, 10):
        assert math.isclose(Tyres(SOFT, laps).wear(), laps * rate)
    assert Tyres(SOFT, 1000).wear() == 1.0
    assert math.isclose(Tyres(SOFT, 1000).grip(), COMPOUNDS[SOFT].grip * (1 - WORN_GRIP_LOSS))
    grips = [Tyres(SOFT, laps).grip() for laps in range(0, 25)]
    assert all(a > b for a, b in zip(grips, grips[1:20])) and grips[20:] == [grips[20]] * 5
    new, worn = (LapProfile(FAST, Stadium(), Tyres(SOFT, laps).grip()).time[-1] for laps in (0, 20))
    assert worn > new


def test_new_softer_tyres_are_faster():
    soft, medium, hard = (LapProfile(FAST, Stadium(), COMPOUNDS[c].grip).time[-1] for c in (SOFT, MEDIUM, HARD))
    assert soft < medium < hard
    assert math.isclose(medium, lap_time(FAST), rel_tol=1e-12)


def test_fuel_burns_every_lap_and_its_mass_slows_the_car():
    car = RaceCar(1, "Solo", FAST, Strategy(MEDIUM, 10.0))
    race = Race(Stadium(), 4, [car], fuel_per_lap=2.0)
    fuel_by_lap = {}
    while not race.finished:
        race.step(0.5)
        fuel_by_lap[car.laps] = car.fuel
    assert fuel_by_lap == {0: 10.0, 1: 8.0, 2: 6.0, 3: 4.0, 4: 2.0}
    light, heavy = (LapProfile(FAST, Stadium(), fuel=fuel).time[-1] for fuel in (0.0, 100.0))
    assert heavy > light


def test_pit_stop_costs_pit_loss_and_fits_new_tyres():
    no_wear = dict(fuel_per_lap=0.0, compounds=V1_TYRES, pit_loss=20.0)
    plain, _ = solo(Strategy(MEDIUM, 0.0), **no_wear)
    stopped, race = solo(Strategy(MEDIUM, 0.0, (PitStop(2, MEDIUM),)), **no_wear)
    assert math.isclose(stopped.finish_time - plain.finish_time, 20.0, rel_tol=1e-9)
    [event] = race.pit_events
    assert (event.number, event.lap, event.duration, event.fuel_added) == (1, 2, 20.0, 0.0)
    assert math.isclose(event.time, 2 * lap_time(FAST), rel_tol=1e-9)
    assert event.tyres_before == Tyres(MEDIUM, 2) and event.tyres_after == Tyres(MEDIUM, 0)
    assert stopped.tyres == Tyres(MEDIUM, 2)  # laps 3 and 4 on the new set


def test_car_stands_still_in_the_pits():
    car = RaceCar(1, "Solo", FAST, Strategy(MEDIUM, 10.0, (PitStop(1, HARD),)))
    race = Race(Stadium(), 3, [car], pit_loss=20.0)
    while car.laps < 1:
        race.step(0.5)
    race.step(15.0)
    assert car.distance == LENGTH and race.time < car.pit_exit
    race.step(10.0)
    assert car.distance > LENGTH and car.tyres.compound is HARD


def test_refuelling_adds_fuel_and_stationary_time():
    car, race = solo(Strategy(MEDIUM, 4.0, (PitStop(2, fuel=5.0),)), fuel_per_lap=1.9)
    [event] = race.pit_events
    assert math.isclose(event.duration, race.pit_loss + 5.0 / REFUEL_RATE)
    assert event.tyres_after == event.tyres_before == Tyres(MEDIUM, 2)  # fuel only: tyres stay on
    assert math.isclose(car.fuel, 4.0 - 4 * 1.9 + 5.0)


def test_impossible_pit_plans_are_rejected():
    impossible = [
        Strategy(MEDIUM, 10.0, (PitStop(0, HARD),)),  # before the race
        Strategy(MEDIUM, 10.0, (PitStop(4, HARD),)),  # as the car finishes
        Strategy(MEDIUM, 10.0, (PitStop(9, HARD),)),  # after the finish
        Strategy(MEDIUM, 10.0, (PitStop(2.5, HARD),)),  # not a lap
        Strategy(MEDIUM, 10.0, (PitStop(2, HARD), PitStop(2, SOFT))),  # two stops in one lap
        Strategy(MEDIUM, 10.0, (PitStop(2, TyreCompound.WET),)),  # not in the race's (dry-only) table
        Strategy(MEDIUM, 10.0, (PitStop(2),)),  # changes nothing
        Strategy(MEDIUM, 10.0, (PitStop(2, HARD, -1.0),)),  # removes fuel
        Strategy(MEDIUM, -1.0),  # negative start fuel
        Strategy(MEDIUM, FUEL_CAPACITY + 1),  # over the tank size
        Strategy(MEDIUM, 3 * 1.9),  # runs dry on lap 4
        Strategy(MEDIUM, 2 * 1.9, (PitStop(2, fuel=1.0),)),  # refuels too little, runs dry on lap 3
        Strategy(MEDIUM, FUEL_CAPACITY, (PitStop(1, fuel=5.0),)),  # overfills the tank
    ]
    for strategy in impossible:
        with assert_raises(ValueError):
            Race(Stadium(), 4, [RaceCar(1, "A", FAST, strategy)], fuel_per_lap=1.9, compounds=DRY_COMPOUNDS)
    for settings in (dict(pit_loss=-1.0), dict(fuel_per_lap=-0.1)):
        with assert_raises(ValueError):
            Race(Stadium(), 4, [RaceCar(1, "A", FAST)], **settings)


def test_strategy_is_followed_across_the_race():
    plan = Strategy(SOFT, 6 * 1.9, (PitStop(2, MEDIUM), PitStop(4, HARD, 2.0)))
    car, race = solo(plan, laps=7, fuel_per_lap=1.9)
    assert [(e.lap, e.tyres_before, e.tyres_after.compound) for e in race.pit_events] == [
        (2, Tyres(SOFT, 2), MEDIUM),
        (4, Tyres(MEDIUM, 2), HARD),
    ]
    assert car.tyres == Tyres(HARD, 3) and car.laps == 7
    assert math.isclose(car.fuel, 6 * 1.9 + 2.0 - 7 * 1.9)
    assert race.pit_events[0].time < race.pit_events[1].time < car.finish_time


def test_default_plan_is_no_stop_on_mediums_with_just_enough_fuel():
    car, race = solo(None, laps=4, fuel_per_lap=1.9)
    assert race.pit_events == [] and car.tyres == Tyres(MEDIUM, 4)
    assert math.isclose(car.fuel, 0.0, abs_tol=1e-9)


def test_which_strategy_wins_depends_on_wear_and_pit_loss():
    no_stop = Strategy(MEDIUM, 0.0)
    one_stop = Strategy(MEDIUM, 0.0, (PitStop(5, MEDIUM),))

    def gap(compounds, pit_loss):  # > 0 when stopping pays off
        times = [solo(plan, laps=10, fuel_per_lap=0.0, compounds=compounds, pit_loss=pit_loss)[0].finish_time
                 for plan in (no_stop, one_stop)]
        return times[0] - times[1]

    assert gap(V1_TYRES, 20.0) < 0  # no wear: a stop is pure loss
    assert gap({MEDIUM: Compound(TYRE_GRIP, wear_per_lap=0.1)}, 1.0) > 0  # heavy wear, cheap stop


def test_results_with_stops_are_deterministic_and_independent_of_step_size():
    def result(dt):
        grid = [RaceCar(1, "A", FAST, Strategy(SOFT, 6 * 1.9, (PitStop(3, HARD, 1.0),))),
                RaceCar(2, "B", FAST, Strategy(HARD, 6 * 1.9))]
        race = Race(Stadium(), 6, grid, traffic=None)  # V2 exactness: cars ignore each other
        race.run(dt)
        return [car.finish_time for car in grid], race.pit_events

    assert result(0.5) == result(0.5)
    (coarse, coarse_stops), (fine, fine_stops) = result(3.0), result(0.05)
    assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(coarse, fine))
    assert math.isclose(coarse_stops[0].time, fine_stops[0].time, abs_tol=1e-6)



def test_v2_race_results_unchanged_without_traffic():
    # recorded from V2 (commit 908961f): four cars, two with stops, cars ignore each other
    grid = [RaceCar(1, "A", SLOW, Strategy(HARD, 8 * 1.9)),
            RaceCar(2, "A", SLOW, Strategy(SOFT, 8 * 1.9, (PitStop(4, MEDIUM),))),
            RaceCar(3, "B", FAST, Strategy(MEDIUM, 4 * 1.9, (PitStop(4, HARD, 4 * 1.9),))),
            RaceCar(4, "B", FAST)]
    race = Race(Stadium(), 8, grid, traffic=None)
    race.run(0.5)
    v2 = {1: 205.0533860528629, 2: 225.57606833293937, 3: 215.8975745239068, 4: 193.32503984524195}
    assert all(math.isclose(car.finish_time, v2[car.number], abs_tol=1e-6) for car in grid)
    assert [(e.number, e.lap) for e in race.pit_events] == [(3, 4), (2, 4)]
    assert math.isclose(race.pit_events[0].time, 96.54882910906912, abs_tol=1e-6)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
