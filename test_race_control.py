import math
from unittest import TestCase

from abstract_classes import TyreCompound
from drivers import Driver
from race import Race, RaceCar
from race_control import TRANSITIONS, Flag, Incident, Penalty, RaceControl, RaceControlRules, check_transition
from strategy import PitStop, Strategy
from test_race import FAST, SLOW, V1_TYRES
from test_simulation import Stadium
from traffic import TrafficRules
from weather import Weather, WeatherPoint

assert_raises = TestCase().assertRaises
MEDIUM, HARD, SOFT = TyreCompound.MEDIUM, TyreCompound.HARD, TyreCompound.SOFT
NO_RULE = RaceControlRules(two_compound_penalty=0.0)
SIMPLE = dict(fuel_per_lap=0.0, compounds=V1_TYRES, traffic=None)  # no fuel, wear or traffic: pure timing


def run(grid, laps, control, dt=0.1, **settings):
    race = Race(Stadium(), laps, grid, race_control=control, **settings)
    history = []
    while not race.finished:
        race.step(dt)
        history.append((race.time, control.flag, {car.number: car.distance for car in grid}))
    return race, history


def flag_changes(control):
    return [(e.time, e.detail.split(":")[0]) for e in control.events if e.kind == "flag"]


def near(time, expected):  # scripted times are applied at the first step that reaches them
    return expected - 1e-9 <= time <= expected + 0.1 + 1e-9


def test_transition_table():
    for old in Flag:
        for new in Flag:
            if new in TRANSITIONS[old]:
                check_transition(old, new)
            else:
                with assert_raises(ValueError):
                    check_transition(old, new)
    assert all(Flag.GREEN in TRANSITIONS[state] for state in Flag if state is not Flag.GREEN)  # every flag can end
    assert TRANSITIONS[Flag.SAFETY_CAR] == {Flag.GREEN}  # no downgrade from the safety car


def test_escalation_extension_and_invalid_clear():
    control = RaceControl()
    with assert_raises(ValueError):
        control.clear(0.0, (), "already green")
    control.call(Flag.YELLOW, 10.0, 20.0, 3, (), "a")
    control.call(Flag.YELLOW, 15.0, 30.0, 5, (), "b")  # same flag: extended, zone kept
    assert (control.flag, control.zone, control.ends_at) == (Flag.YELLOW, 3, 45.0)
    control.call(Flag.SAFETY_CAR, 20.0, 60.0, None, (), "c")
    control.call(Flag.VSC, 25.0, 10.0, None, (), "d")  # lower flag: the safety car stays
    assert (control.flag, control.zone, control.ends_at) == (Flag.SAFETY_CAR, None, 80.0)
    assert [e.kind for e in control.events] == ["flag", "extended", "flag", "extended"]


def test_scripted_items_are_validated():
    bad_incidents = [dict(time=-1, flag=Flag.VSC, duration=10), dict(time=0, flag=Flag.GREEN, duration=10),
                     dict(time=0, flag=Flag.VSC, duration=0), dict(time=0, flag=Flag.VSC, duration=math.inf),
                     dict(time=0, flag=Flag.VSC, duration=math.nan), dict(time=0), dict(time=0, flag=Flag.YELLOW, duration=5)]
    for kwargs in bad_incidents:
        with assert_raises(ValueError):
            Incident(**kwargs)
    for kwargs in (dict(time=-1, car=1), dict(time=0, car=1, kind="grid"), dict(time=0, car=1, seconds=0)):
        with assert_raises(ValueError):
            Penalty(**kwargs)
    grid = lambda: [RaceCar(1, "A", FAST)]
    for control in (RaceControl([Incident(5, retire=9)]), RaceControl(penalties=[Penalty(5, 9)]),
                    RaceControl([Incident(5, Flag.YELLOW, 10, segment=4)])):  # Stadium has segments 0-3
        with assert_raises(ValueError):
            Race(Stadium(), 3, grid(), race_control=control)
    used = RaceControl([Incident(1, Flag.VSC, 5)])
    run(grid(), 2, used, **SIMPLE)
    with assert_raises(ValueError):
        Race(Stadium(), 3, grid(), race_control=used)


def test_yellow_slows_only_its_segment_and_clears_after_its_duration():
    rules = NO_RULE
    assert RaceControl(rules=rules).pace_factor(1.0, in_zone=True, leads=True) == 1.0  # green: no effect
    control = RaceControl([Incident(5.0, Flag.YELLOW, 20.0, segment=0, reason="debris")], rules=rules)
    assert math.isclose(control.pace_factor(1.0, True, True), 1.0)  # still green until the race applies it
    car = RaceCar(1, "A", FAST)
    race, history = run([car], 3, control, **SIMPLE)
    [(on, first), (off, second)] = flag_changes(control)
    assert (first, second) == ("GREEN -> YELLOW", "YELLOW -> GREEN") and near(on, 5.0) and near(off, 25.0)
    yellow = RaceControl([Incident(5.0, Flag.YELLOW, 20.0, segment=0)], rules=rules)
    yellow.flag, yellow.zone = Flag.YELLOW, 0
    assert math.isclose(yellow.pace_factor(1.0, True, False), 1.1) and yellow.pace_factor(1.0, False, False) == 1.0
    assert not yellow.overtaking_allowed(in_zone=True) and yellow.overtaking_allowed(in_zone=False)
    plain, _ = run([RaceCar(1, "A", FAST)], 3, RaceControl(rules=rules), **SIMPLE)
    lost = car.finish_time - plain.cars[0].finish_time
    assert 0 < lost < 20 * 0.1 + 0.2  # at most 10 % of the 20 s, and only while inside segment 0


def test_vsc_slows_every_car_by_its_factor_and_nobody_passes():
    car = RaceCar(1, "A", FAST)
    run([car], 4, RaceControl([Incident(20.0, Flag.VSC, 60.0)], rules=NO_RULE), **SIMPLE)
    plain = RaceCar(1, "A", FAST)
    run([plain], 4, RaceControl(rules=NO_RULE), **SIMPLE)
    assert math.isclose(car.finish_time - plain.finish_time, 60.0 * (1 - 1 / 1.4), abs_tol=0.15)
    slow, fast = RaceCar(1, "S", SLOW), RaceCar(2, "F", FAST)
    control = RaceControl([Incident(0.0, Flag.VSC, 300.0)], rules=NO_RULE)
    race, history = run([slow, fast], 3, control, traffic=TrafficRules())
    vsc_steps = [d for t, flag, d in history if flag is Flag.VSC and slow.finish_time is None]
    assert all(d[1] >= d[2] for d in vsc_steps)  # the faster car stays behind under VSC
    assert not [e for e in race.overtakes if e.outcome == "passed"]


def test_safety_car_bunches_the_field_freezes_order_and_ends_at_the_line():
    grid = [RaceCar(1, "A", FAST), RaceCar(2, "B", FAST, driver=Driver(pace=0.0)), RaceCar(3, "C", SLOW)]
    control = RaceControl([Incident(60.0, Flag.SAFETY_CAR, 40.0, reason="crash")], rules=NO_RULE)
    race, history = run(grid, 8, control, traffic=None)
    before = next(d for t, flag, d in history if t >= 60.0)
    assert before[1] - before[3] > 100  # spread out before the safety car
    under_sc = [(t, d) for t, flag, d in history if flag is Flag.SAFETY_CAR]
    assert all(d[1] > d[2] > d[3] for _, d in under_sc)  # order frozen
    end_gap = under_sc[-1][1]
    assert end_gap[1] - end_gap[2] <= 10.0 + 1e-6 and end_gap[2] - end_gap[3] <= 10.0 + 1e-6  # bunched to sc_gap
    [(start, _), (clear, _)] = flag_changes(control)
    assert near(start, 60.0) and clear >= 100.0
    lap_length = Stadium().length
    leader_at_clear = next(d for t, flag, d in history if t == clear)[1]
    assert leader_at_clear % lap_length < 100  # it ended as the leader crossed the line


def test_retired_car_stops_drops_to_the_bottom_and_the_race_still_ends():
    leader, second = RaceCar(1, "A", FAST), RaceCar(2, "B", SLOW)
    control = RaceControl([Incident(30.0, retire=1, reason="engine")], rules=NO_RULE)
    race = Race(Stadium(), 3, [leader, second], race_control=control, **SIMPLE)
    while leader.retired_at is None:
        race.step(0.1)
    stopped_at = leader.distance
    assert second.distance < stopped_at  # still behind on the road ...
    assert race.standings() == [second, leader] and race.car_ahead(second) is None  # ... but ahead, and not blocked
    race.run(0.1)
    assert leader.distance == stopped_at and race.finished
    assert leader.finish_time is None and second.finish_time is not None
    assert race.standings() == [second, leader] and race.laps_completed(leader) == 1
    [event] = control.events
    assert (event.kind, event.cars, event.flag) == ("retirement", (1,), Flag.GREEN)


def test_pass_in_progress_is_abandoned_when_flags_come_out():
    def race(incidents):
        slow, fast = RaceCar(1, "S", SLOW), RaceCar(2, "F", FAST)
        r = Race(Stadium(), 3, [slow, fast], race_control=RaceControl(incidents, rules=NO_RULE))
        attack_started = None
        while not r.finished:
            r.step(0.1)
            if fast.attack and attack_started is None:
                attack_started = r.time
        return r, attack_started

    clean, started = race([])
    assert started is not None
    flagged, _ = race([Incident(started + 0.05, Flag.VSC, 10.0)])  # VSC called mid-pass
    [(vsc_on, _), (vsc_off, _)] = flag_changes(flagged.race_control)
    outcomes = [(e.outcome, e.time) for e in flagged.overtakes if e.attacker == 2]
    assert outcomes[0][0] == "aborted" and vsc_on < outcomes[0][1] <= vsc_on + 0.1 + 1e-9  # dropped in that step
    passed = [t for outcome, t in outcomes if outcome == "passed"]
    assert passed and passed[0] > vsc_off  # completed only after the VSC


def test_time_penalty_reorders_the_classification():
    a, b = RaceCar(1, "A", FAST), RaceCar(2, "B", FAST, driver=Driver(pace=0.9))
    control = RaceControl(penalties=[Penalty(10.0, 1, "time", 5.0, "track limits")], rules=NO_RULE)
    race, _ = run([a, b], 3, control, **SIMPLE)
    assert a.finish_time < b.finish_time < a.finish_time + 5  # first on the road
    assert race.total_time(a) == a.finish_time + 5 and race.standings() == [b, a]


def test_drive_through_is_served_under_green_or_converted_at_the_flag():
    def finish(penalties, incidents=()):
        car = RaceCar(1, "A", FAST)
        control = RaceControl(incidents, penalties, rules=NO_RULE)
        race, _ = run([car], 4, control, **SIMPLE)
        return car, race, control

    plain, *_ = finish([])
    served, _, control = finish([Penalty(5.0, 1, "drive-through", reason="unsafe release")])
    assert math.isclose(served.finish_time - plain.finish_time, 20.0, abs_tol=1e-6)
    assert [e.kind for e in control.events] == ["penalty", "penalty served"] and served.penalty_time == 0
    late, race, control = finish([Penalty(80.0, 1, "drive-through")])  # issued on the last lap
    assert late.penalty_time == 20.0 and control.events[-1].kind == "penalty converted"
    assert race.total_time(late) == late.finish_time + 20.0
    under_sc, _, control = finish([Penalty(5.0, 1, "drive-through")], [Incident(4.0, Flag.SAFETY_CAR, 50.0)])
    kinds = [(e.kind, e.detail.split(":")[0]) for e in control.events]
    assert kinds.index(("flag", "SAFETY_CAR -> GREEN")) < kinds.index(("penalty served", "#1 drive-through after lap 3"))


def test_penalty_for_a_retired_car_is_ignored():
    car, other = RaceCar(1, "A", FAST), RaceCar(2, "B", FAST)
    control = RaceControl([Incident(5.0, retire=1)], [Penalty(10.0, 1, "time", 5.0)], rules=NO_RULE)
    run([car, other], 2, control, **SIMPLE)
    assert car.penalty_time == 0 and [e.kind for e in control.events] == ["retirement", "ignored"]


def test_two_dry_compound_rule():
    def penalty(strategy, weather=None, rules=RaceControlRules()):
        car = RaceCar(1, "A", FAST, strategy)
        race = Race(Stadium(), 4, [car], race_control=RaceControl(rules=rules), traffic=None, weather=weather)
        race.run(0.5)
        return car.penalty_time

    assert penalty(Strategy(MEDIUM, 4 * 1.9)) == 30.0
    assert penalty(Strategy(MEDIUM, 4 * 1.9, (PitStop(2, HARD),))) == 0.0
    assert penalty(Strategy(MEDIUM, 4 * 1.9, (PitStop(2, MEDIUM),))) == 30.0  # a fresh set of the same compound
    assert penalty(Strategy(TyreCompound.INTERMEDIATE, 4 * 1.9)) == 0.0  # wet tyres used: exempt
    assert penalty(Strategy(MEDIUM, 4 * 1.9), rules=NO_RULE) == 0.0


def test_events_are_logged_in_time_order_with_the_cars_affected():
    grid = [RaceCar(1, "A", FAST), RaceCar(2, "B", FAST), RaceCar(3, "C", SLOW)]
    control = RaceControl(
        [Incident(40.0, Flag.VSC, 15.0, retire=3, reason="stopped car"), Incident(20.0, Flag.YELLOW, 5.0, segment=1)],
        [Penalty(40.0, 2, "time", 5.0), Penalty(30.0, 1, "drive-through")],
        rules=NO_RULE,
    )
    run(grid, 5, control, **SIMPLE)
    times = [e.time for e in control.events]
    assert times == sorted(times)
    kinds = [(e.kind, e.cars) for e in control.events if 39.9 < e.time < 40.2]
    assert kinds == [("retirement", (3,)), ("flag", (1, 2)), ("penalty", (2,))]  # incident, then its flag, then penalty
    assert all(e.flag is Flag.VSC for e in control.events if e.kind == "penalty" and e.time > 39.9 and e.time < 41)


def test_pit_stop_under_vsc_costs_less_than_under_green():
    def relative_loss(incidents):
        stopper = RaceCar(1, "A", FAST, Strategy(MEDIUM, 0.0, (PitStop(2, MEDIUM),)))
        stayer = RaceCar(2, "B", FAST)
        run([stopper, stayer], 4, RaceControl(incidents, rules=NO_RULE), **SIMPLE)
        return stopper.finish_time - stayer.finish_time

    green = relative_loss([])
    vsc = relative_loss([Incident(45.0, Flag.VSC, 40.0)])  # covers the stop after lap 2 (~48 s)
    assert vsc < green - 3


def test_drs_needs_green_flags_and_a_dry_enough_track():
    def drs_laps(weather=None, incidents=()):
        grid = [RaceCar(1, "A", FAST), RaceCar(2, "B", FAST)]
        race = Race(Stadium(), 6, grid, weather=weather, race_control=RaceControl(incidents, rules=NO_RULE))
        seen = set()
        while not race.finished:
            race.step(0.1)
            if grid[1].drs:
                seen.add(grid[1].laps + 1)
        return seen

    assert drs_laps()  # dry and green: the follower gets DRS
    wet = Weather([WeatherPoint(0, 20.0)], wetness=0.6)  # stays above 0.3 for this short race
    assert drs_laps(weather=wet) == set()
    assert not drs_laps(incidents=[Incident(0.0, Flag.VSC, 1000.0)])


def test_no_passes_under_safety_car_and_racing_resumes_after():
    slow, fast = RaceCar(1, "S", SLOW), RaceCar(2, "F", FAST)
    control = RaceControl([Incident(0.0, Flag.SAFETY_CAR, 30.0)], rules=NO_RULE)
    race, history = run([slow, fast], 4, control)
    [(_, _), (clear, _)] = flag_changes(control)
    passes = [e.time for e in race.overtakes if e.outcome == "passed"]
    assert passes and min(passes) > clear  # held under the safety car, passes after the restart


def test_v4_race_results_unchanged_without_race_control():
    # recorded from V4 (commit 22b3668): traffic, weather and stops
    def race(control):
        grid = [RaceCar(1, "A", FAST, Strategy(MEDIUM, 12 * 1.9, react_to_weather=True)),
                RaceCar(2, "B", FAST, Strategy(SOFT, 12 * 1.9, (PitStop(3, HARD),))), RaceCar(3, "C", SLOW)]
        weather = Weather([WeatherPoint(0, 22.0), WeatherPoint(80, 22.0), WeatherPoint(90, 22.0, 15.0),
                           WeatherPoint(200, 22.0, 15.0), WeatherPoint(210, 22.0)])
        r = Race(Stadium(), 12, grid, weather=weather, race_control=control)
        r.run(0.1)
        return r, grid

    r, grid = race(None)
    v4 = {1: 348.5735497744607, 2: 380.1961773754289, 3: 364.8950297099013}
    assert all(math.isclose(car.finish_time, v4[car.number], abs_tol=1e-6) for car in grid)
    assert [(e.number, e.lap) for e in r.pit_events] == [(2, 3), (1, 6)] and len(r.overtakes) == 4
    quiet = RaceControl(rules=RaceControlRules(two_compound_penalty=0.0, drs_max_wetness=1.0))
    r2, grid2 = race(quiet)  # race control with nothing to do changes nothing
    assert [car.finish_time for car in grid2] == [car.finish_time for car in grid] and r2.overtakes == r.overtakes


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
