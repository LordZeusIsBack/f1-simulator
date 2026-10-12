import math
from unittest import TestCase

from abstract_classes import TyreCompound
from race import WETNESS_STEP, LapProfile, Race, RaceCar
from strategy import PitStop, Strategy
from test_race import FAST
from test_simulation import Stadium
from tyres import COMPOUNDS, DRY_COMPOUNDS, Tyres, best_compound
from weather import DRYING_RATE, SUN_HEATING, WETTING_RATE, Weather, WeatherPoint

assert_raises = TestCase().assertRaises
SOFT, MEDIUM, HARD = TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD
INTER, WET = TyreCompound.INTERMEDIATE, TyreCompound.WET
DRY_DAY = [WeatherPoint(0, 25.0)]


def crossover(a, b):
    """Wetness at which new sets of compounds a and b have equal grip (linear wet_loss model)."""
    ca, cb = COMPOUNDS[a], COMPOUNDS[b]
    return (ca.grip - cb.grip) / (ca.grip * ca.wet_loss - cb.grip * cb.wet_loss)


def wetness_trace(weather, seconds, dt=0.1):
    values = [weather.wetness]
    for _ in range(round(seconds / dt)):
        values.append(weather.advance(dt).wetness)
    return values


def test_weather_points_and_state_are_validated():
    for good in (WeatherPoint(0, -10.0), WeatherPoint(0, 50.0, 0.0), WeatherPoint(5, 20.0, 50.0)):
        assert good.time >= 0
    bad_points = [(-1, 20, 0), (0, -10.1, 0), (0, 50.1, 0), (0, 20, -0.1), (0, 20, 50.1), (math.nan, 20, 0), (0, math.nan, 0)]
    for time, air, rain in bad_points:
        with assert_raises(ValueError):
            WeatherPoint(time, air, rain)
    for timeline in ([], [WeatherPoint(10, 20), WeatherPoint(5, 20)], [WeatherPoint(5, 20), WeatherPoint(5, 21)]):
        with assert_raises(ValueError):
            Weather(timeline)
    for wetness in (-0.01, 1.01, math.nan):
        with assert_raises(ValueError):
            Weather(DRY_DAY, wetness)
    for wetness in (0.0, 1.0):
        c = Weather(DRY_DAY, wetness).conditions
        assert (c.time, c.air_temp, c.rain, c.wetness) == (0.0, 25.0, 0.0, wetness)
        assert c.track_temp == 25.0 + SUN_HEATING * (1 - wetness)  # 40 °C dry, 25 °C fully wet


def test_timeline_is_held_before_and_after_and_linear_between():
    weather = Weather([WeatherPoint(100, 20.0, 0.0), WeatherPoint(200, 10.0, 8.0)])
    seen = {}
    for _ in range(3000):
        c = weather.advance(0.1)
        seen[round(c.time, 1)] = (c.air_temp, c.rain)
    assert seen[50.0] == (20.0, 0.0) and seen[300.0] == (10.0, 8.0)
    air, rain = seen[150.0]
    assert math.isclose(air, 15.0) and math.isclose(rain, 4.0)


def test_rain_wets_the_track_gradually_up_to_a_balance_and_never_past_one():
    weather = Weather([WeatherPoint(0, 20.0, 50.0)])  # heaviest rain allowed
    trace = wetness_trace(weather, 600)
    assert all(b > a for a, b in zip(trace, trace[1:300]))  # rising, step by step
    assert max(b - a for a, b in zip(trace, trace[1:])) < 0.01  # no jump bigger than 0.01 per 0.1 s
    assert trace[-1] < 1.0
    c = weather.conditions  # settled: wetting and drying cancel out
    k_wet, k_dry = WETTING_RATE * c.rain, DRYING_RATE * c.track_temp
    assert math.isclose(c.wetness, k_wet / (k_wet + k_dry), rel_tol=1e-6)


def test_track_dries_without_rain_faster_when_warmer_and_not_at_all_at_zero_degrees():
    def dried(air):
        return wetness_trace(Weather([WeatherPoint(0, air)], wetness=1.0), 300)

    hot, cool = dried(40.0), dried(10.0)
    assert all(b < a for a, b in zip(hot, hot[1:])) and hot[-1] < cool[-1] < 1.0
    assert dried(0.0)[-1] == 1.0  # a wet track at 0 °C (air 0 + 15 × (1 − 1)) does not dry
    assert dried(-10.0)[-1] == 1.0
    cold_rain = wetness_trace(Weather([WeatherPoint(0, -10.0, 5.0)]), 3000)  # no drying below 0 °C: rain alone
    assert max(cold_rain) <= 1.0 and cold_rain[-1] > 0.999
    assert wetness_trace(Weather(DRY_DAY), 300)[-1] == 0.0  # dry and no rain: stays dry


def test_wetness_costs_slicks_far_more_grip_than_wet_tyres():
    for compound in COMPOUNDS:
        assert Tyres(compound).grip(COMPOUNDS, 0.0) == COMPOUNDS[compound].grip == Tyres(compound).grip()
    dry = {c: Tyres(c).grip(COMPOUNDS, 0.0) for c in (MEDIUM, INTER, WET)}
    wet = {c: Tyres(c).grip(COMPOUNDS, 1.0) for c in (MEDIUM, INTER, WET)}
    assert dry[MEDIUM] > dry[INTER] > dry[WET] and wet[WET] > wet[INTER] > wet[MEDIUM]
    assert math.isclose(wet[MEDIUM], 1.8 * (1 - 0.65))
    slick_lap, wet_lap = (LapProfile(FAST, Stadium(), wet[c]).time[-1] for c in (MEDIUM, WET))
    assert wet_lap < slick_lap  # on a soaked track the wet tyre is faster round a lap


def test_best_compound_changes_with_wetness_at_the_documented_crossovers():
    slick_to_inter, inter_to_wet = crossover(SOFT, INTER), crossover(INTER, WET)
    assert 0.35 < slick_to_inter < 0.45 and 0.6 < inter_to_wet < 0.75
    assert best_compound(COMPOUNDS, 0.0) is SOFT
    assert best_compound(COMPOUNDS, slick_to_inter - 1e-9) is SOFT
    assert best_compound(COMPOUNDS, slick_to_inter + 1e-9) is INTER
    assert best_compound(COMPOUNDS, inter_to_wet - 1e-9) is INTER
    assert best_compound(COMPOUNDS, inter_to_wet + 1e-9) is WET
    assert best_compound(COMPOUNDS, 1.0) is WET
    assert best_compound(DRY_COMPOUNDS, 1.0) is SOFT  # only slicks available


def test_weather_aware_strategy_asks_for_the_right_tyres():
    plan = Strategy(MEDIUM, 10.0, (PitStop(3, HARD),), react_to_weather=True)
    assert plan.stop_after(1, Tyres(MEDIUM, 1), 0.6) == PitStop(1, INTER)
    assert plan.stop_after(1, Tyres(MEDIUM, 1), 0.4) is None  # inters better, but by less than the margin
    assert plan.stop_after(1, Tyres(INTER, 5), 0.95) == PitStop(1, WET)
    assert plan.stop_after(1, Tyres(INTER, 5), 0.1) == PitStop(1, SOFT)  # dried out: back to slicks
    assert plan.stop_after(3, Tyres(MEDIUM, 3), 0.9) == PitStop(3, HARD)  # the planned stop comes first
    assert Strategy(MEDIUM, 10.0).stop_after(1, Tyres(MEDIUM, 1), 0.9) is None  # fixed plans ignore weather


def test_rain_during_a_race_slows_slicks_and_a_weather_aware_car_switches():
    def race(timeline, *plans):
        grid = [RaceCar(n, "T", FAST, plan) for n, plan in enumerate(plans, start=1)]
        weather = Weather(timeline) if timeline else None
        r = Race(Stadium(), 20, grid, traffic=None, weather=weather)
        r.run(0.1)
        return r, grid

    shower = [WeatherPoint(0, 22.0), WeatherPoint(60, 22.0), WeatherPoint(70, 22.0, 20.0)]
    stays = Strategy(MEDIUM, 20 * 1.9)
    reacts = Strategy(MEDIUM, 20 * 1.9, react_to_weather=True)
    wet, (slick_car, smart_car) = race(shower, stays, reacts)
    _, (dry_car,) = race(None, stays)

    kinds = [(e.kind, e.best) for e in wet.weather_events]
    assert kinds[0] == ("rain starts", SOFT) and ("best tyres", INTER) in kinds and ("best tyres", WET) in kinds
    assert [e.time for e in wet.weather_events] == sorted(e.time for e in wet.weather_events)
    assert slick_car.finish_time > dry_car.finish_time + 20  # same plan, much slower in the rain
    assert [stop.number for stop in wet.pit_events] == [2, 2]
    assert [stop.tyres_after.compound for stop in wet.pit_events] == [INTER, WET]
    assert smart_car.finish_time < slick_car.finish_time - 60  # two stops pay off over 20 laps


def test_lap_profiles_follow_wetness_within_one_step_of_resolution():
    car = RaceCar(1, "T", FAST, Strategy(MEDIUM, 3 * 1.9))
    race = Race(Stadium(), 3, [car], traffic=None, weather=Weather([WeatherPoint(0, 20.0, 30.0)]))
    lap_times = set()
    while not race.finished:
        race.step(0.1)
        assert abs(race.weather.wetness - race._grip_wetness) < WETNESS_STEP + 0.01
        if car.laps == 0:
            lap_times.add(race._profiles[1].time[-1])
    assert len(lap_times) > 3  # rebuilt several times before the end of the first lap


def test_drying_track_logs_rain_free_change_back_to_slicks():
    weather = Weather([WeatherPoint(0, 35.0)], wetness=crossover(SOFT, INTER) + 0.02)
    race = Race(Stadium(), 4, [RaceCar(1, "T", FAST, Strategy(INTER, 4 * 1.9))], traffic=None, weather=weather)
    race.run(0.1)
    assert [(e.kind, e.best) for e in race.weather_events] == [("best tyres", SOFT)]


def test_dry_weather_gives_the_same_race_as_no_weather():
    def result(weather):
        grid = [RaceCar(1, "A", FAST), RaceCar(2, "B", FAST, Strategy(SOFT, 5 * 1.9, (PitStop(2, HARD),)))]
        race = Race(Stadium(), 5, grid, weather=weather)
        race.run(0.1)
        return [car.finish_time for car in grid], race.overtakes, race.weather_events

    assert result(Weather(DRY_DAY)) == result(None)


def test_weather_must_be_fresh_for_each_race():
    weather = Weather(DRY_DAY)
    weather.advance(1.0)
    with assert_raises(ValueError):
        Race(Stadium(), 3, [RaceCar(1, "A", FAST)], weather=weather)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
