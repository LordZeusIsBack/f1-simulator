"""P2-V3: pedals, the physics that executes them, the braking look-ahead, controlled cars in a race, and driving
policies changing how a car moves. Every behaviour test checks speed, distance or time, not just the pedal values."""
import math
from unittest import TestCase

from abstract_classes import TyreCompound
from control import (COAST, FULL_BRAKE, FULL_THROTTLE, MAX_CONTROL_STEP, STYLES, CarControl, Control,
                     braking_envelope, step_motion, track_speed)
from drivers import Driver
from driving import Decision, DriverAction, observe, run
from physics import corner_speed
from race import Race, RaceCar
from race_control import Flag, Incident, RaceControl
from simulation import simulate_lap
from strategy import PitStop, Strategy
from test_race import FAST, SLOW, V1_TYRES
from test_simulation import Stadium

assert_raises = TestCase().assertRaises
A = DriverAction
SPEC, GRIP = FAST.specification, V1_TYRES[TyreCompound.MEDIUM].grip
STRAIGHT, UPHILL = (1.0, math.inf, 0.0, 0.0), (1.0, math.inf, 10.0, 0.0)
CORNER_LIMIT = corner_speed(SPEC, 50, GRIP)  # Stadium's corners: radius 50 m


def solo(action=A.ATTACK, laps=3, control_step=0.02, **settings):
    """One controlled car on Stadium, no fuel burn or wear, so laps are comparable with simulate_lap."""
    car = RaceCar(1, "X", FAST, control=CarControl(action))
    race = Race(Stadium(), laps, [car], fuel_per_lap=0.0, compounds=V1_TYRES, traffic=None, control_step=control_step,
                **settings)
    return race, car


def trace(race, car, dt=0.02):
    """(lap distance, speed) after every step until the finish."""
    points = []
    while not race.finished:
        race.step(dt)
        points.append((car.distance % race.track.length, car.control.speed))
    return points


# ---- the low-level control model ---------------------------------------------------------------------------------

def test_control_inputs_are_validated():
    for good in (Control(), Control(1, 0), Control(0, 1), Control(0.25, 0.0), Control(0.0, 0.5)):
        assert 0 <= good.throttle <= 1 and 0 <= good.brake <= 1
    for bad in (-0.1, 1.1, math.nan, math.inf, True, "1", None):
        for pedal in ("throttle", "brake"):
            with assert_raises(ValueError):
                Control(**{pedal: bad})
    with assert_raises(ValueError):
        Control(0.5, 0.5)  # both pedals at once
    for h in (0.0, -0.01, MAX_CONTROL_STEP * 1.01, math.nan):
        with assert_raises(ValueError):
            step_motion(SPEC, 50.0, STRAIGHT, GRIP, COAST, h)
    for v in (-1.0, math.inf, math.nan):
        with assert_raises(ValueError):
            step_motion(SPEC, v, STRAIGHT, GRIP, COAST, 0.02)
    for step in (0.0, 0.06):
        with assert_raises(ValueError):
            solo(control_step=step)


def test_throttle_and_brake_change_speed_and_distance():
    h = 0.02
    results = {name: step_motion(SPEC, 50.0, STRAIGHT, GRIP, control, h) for name, control in
               (("full", FULL_THROTTLE), ("half", Control(0.5)), ("coast", COAST), ("brake", FULL_BRAKE))}
    speeds = [results[name][0] for name in ("full", "half", "coast", "brake")]
    assert speeds == sorted(speeds, reverse=True) and speeds[0] > 50.0 > speeds[2] > speeds[3]  # coasting: drag only
    for v_new, ds in results.values():
        assert math.isclose(ds, (50.0 + v_new) / 2 * h)  # trapezoid on distance


def test_repeated_steps_accelerate_to_top_speed_then_brake_to_a_stop_without_reversing():
    v, distance, speeds = 0.0, 0.0, []
    for _ in range(round(60 / 0.02)):  # 60 s of full throttle
        v, ds = step_motion(SPEC, v, STRAIGHT, GRIP, FULL_THROTTLE, 0.02)
        distance += ds
        speeds.append(v)
    assert all(b > a for a, b in zip(speeds, speeds[1:]))  # always faster, but more and more slowly
    top = (SPEC.power / (0.5 * 1.225 * SPEC.drag)) ** (1 / 3)  # power = drag force × speed
    assert top - 0.5 < v < top and speeds[-1] - speeds[-2] < 1e-3
    stopped_at = None
    for step in range(round(20 / 0.02)):
        v, ds = step_motion(SPEC, v, STRAIGHT, GRIP, FULL_BRAKE, 0.02)
        distance += ds
        assert v >= 0
        if v == 0 and stopped_at is None:
            stopped_at = distance
    assert stopped_at is not None and distance == stopped_at  # stays stopped
    assert step_motion(SPEC, 0.0, UPHILL, GRIP, COAST, 0.02) == (0.0, 0.0)  # no rolling back down a hill


def test_speed_controller_matches_reachable_targets():
    lowest = step_motion(SPEC, 50.0, STRAIGHT, GRIP, FULL_BRAKE, 0.02)[0]
    highest = step_motion(SPEC, 50.0, STRAIGHT, GRIP, FULL_THROTTLE, 0.02)[0]
    for target in (lowest + 0.01, 49.9, 50.0, highest - 0.01):  # reachable in one 0.02 s sub-step
        control = track_speed(SPEC, 50.0, target, STRAIGHT, GRIP, 0.02)
        assert math.isclose(step_motion(SPEC, 50.0, STRAIGHT, GRIP, control, 0.02)[0], target, abs_tol=1e-9)
    assert track_speed(SPEC, 50.0, 1000.0, STRAIGHT, GRIP, 0.02) == FULL_THROTTLE  # out of reach: pedal clipped
    assert track_speed(SPEC, 50.0, 0.0, STRAIGHT, GRIP, 0.02) == FULL_BRAKE


# ---- look-ahead and segments -------------------------------------------------------------------------------------

def test_braking_envelope_falls_to_the_corner_limit_before_each_corner():
    envelope = braking_envelope(FAST, Stadium(), GRIP, 0.0)
    assert envelope.point(499.5)[1] == math.inf and envelope.point(500.5)[1] == 50  # straight, then the corner
    assert math.isclose(envelope.target(500.5), CORNER_LIMIT)
    before = [envelope.target(d) for d in range(300, 500, 10)]
    assert all(a > b for a, b in zip(before, before[1:])) and before[0] > CORNER_LIMIT + 10  # brake zone, shrinking
    assert envelope.target(250.0) > envelope.target(450.0)
    gentle = braking_envelope(FAST, Stadium(), GRIP * STYLES[A.CONSERVE_TYRES], 0.0)
    assert all(gentle.target(d) < envelope.target(d) for d in range(0, 1300, 25))


def test_controlled_car_brakes_before_the_corner_and_respects_its_limit():
    race, car = solo(laps=1)
    points = trace(race, car)
    first_straight = [(d, v) for d, v in points if 100 < d < 500]
    peak_at = max(first_straight, key=lambda p: p[1])[0]
    assert 400 < peak_at < 495  # braking starts on the straight, before the corner at 500 m
    assert all(v <= CORNER_LIMIT + 1e-9 for d, v in points if 500 < d < 500 + 50 * math.pi)
    assert car.control.clipped == 0


def test_targets_above_the_grip_limit_are_capped_and_counted():
    original = STYLES[A.ATTACK]
    STYLES[A.ATTACK] = 1.3  # a controller aiming 30 % past the grip: Race must not let the car exceed the limit
    try:
        race, car = solo(laps=1)
        points = trace(race, car)
    finally:
        STYLES[A.ATTACK] = original
    assert car.control.clipped > 0
    assert all(v <= CORNER_LIMIT + 1e-9 for d, v in points if 500 < d < 500 + 50 * math.pi)


# ---- time steps and determinism ----------------------------------------------------------------------------------

def test_lap_times_are_stable_across_sub_steps_and_match_the_profile():
    reference = 3 * simulate_lap(FAST, Stadium())[0]
    times = {}
    for step in (0.005, 0.02, MAX_CONTROL_STEP):
        race, car = solo(control_step=step)
        race.run(0.5)
        times[step] = car.finish_time
        assert car.control.clipped == 0 and car.laps == 3
    assert max(times.values()) - min(times.values()) < 0.002 * reference
    assert all(abs(time / reference - 1) < 0.003 for time in times.values())
    for dt in (0.02, 1.0):  # the race step only sets how often tactics can change
        race, car = solo()
        race.run(dt)
        assert math.isclose(car.finish_time, times[0.02], abs_tol=1e-4)


def test_controlled_race_is_deterministic():
    def replay():
        grid = [RaceCar(1, "A", SLOW), RaceCar(2, "B", FAST, control=CarControl()), RaceCar(3, "C", FAST)]
        race = Race(Stadium(), 4, grid)
        log = run(race, {2: lambda o, d: Decision(A.ATTACK if o.gap_ahead is not None else A.MAINTAIN_PACE, "", {})})
        return [car.finish_time for car in grid], race.overtakes, log

    first = replay()
    assert first == replay()


# ---- actions move the car ----------------------------------------------------------------------------------------

def test_each_action_changes_speed_and_lap_time():
    finish, corner = {}, {}
    for action in A:
        race, car = solo(action, laps=2)
        points = trace(race, car)
        finish[action] = car.finish_time
        corner[action] = min(v for d, v in points if 500 < d < 500 + 50 * math.pi)
    assert finish[A.ATTACK] < finish[A.MAINTAIN_PACE] < finish[A.CONSERVE_TYRES]
    assert finish[A.DEFEND] == finish[A.ATTACK]  # no lateral model: defending drives like attacking
    assert corner[A.ATTACK] > corner[A.MAINTAIN_PACE] > corner[A.CONSERVE_TYRES]
    assert math.isclose(corner[A.CONSERVE_TYRES], corner_speed(SPEC, 50, GRIP * 0.9), rel_tol=1e-6)


def test_a_driving_policy_changes_how_the_car_moves():
    def always(action):
        return lambda observation, driver: Decision(action, "test", {})

    def switching(observation, driver):  # save tyres, then push on the last lap (alone, ATTACK is not available)
        return Decision(A.MAINTAIN_PACE if observation.laps_remaining == 0 else A.CONSERVE_TYRES, "test", {})

    results = {}
    for name, policy in (("maintain", always(A.MAINTAIN_PACE)), ("conserve", always(A.CONSERVE_TYRES)),
                         ("switch", switching)):
        race, car = solo(A.ATTACK, laps=3)  # starts on ATTACK; the policy takes over before the first step
        log = run(race, {1: policy})
        results[name] = (car.finish_time, [record.action for record in log])
    assert results["maintain"][0] < results["switch"][0] < results["conserve"][0]
    assert results["switch"][1] == [A.CONSERVE_TYRES, A.MAINTAIN_PACE]
    grid = [RaceCar(1, "A", SLOW), RaceCar(2, "B", FAST, control=CarControl())]
    race = Race(Stadium(), 2, grid)
    log = run(race, {2: lambda o, d: Decision(A.ATTACK if o.gap_ahead is not None else A.MAINTAIN_PACE, "", {})})
    assert log[0].action is A.ATTACK and grid[1].control.action is A.MAINTAIN_PACE  # last decision: alone in front


def test_observation_reports_the_controlled_speed():
    race, car = solo(laps=2)
    for _ in range(100):
        race.step(0.1)
    assert observe(race, car).speed == car.control.speed


# ---- inside a full race ------------------------------------------------------------------------------------------

def test_uncontrolled_cars_are_unaffected_by_a_controlled_car():
    def finish_of_car_1(control):
        grid = [RaceCar(1, "A", FAST), RaceCar(2, "B", SLOW, control=control)]
        race = Race(Stadium(), 3, grid, traffic=None)
        race.run(0.1)
        return grid[0].finish_time

    assert finish_of_car_1(CarControl()) == finish_of_car_1(None)


def test_controlled_car_is_held_in_traffic_until_it_passes():
    grid = [RaceCar(1, "A", SLOW), RaceCar(2, "B", FAST, control=CarControl(A.ATTACK))]
    race = Race(Stadium(), 5, grid)
    order_changed_at = None
    while not race.finished:
        race.step(0.1)
        if order_changed_at is None and grid[1].distance > grid[0].distance:
            order_changed_at = race.time
    events = [(e.outcome, round(e.time, 6)) for e in race.overtakes]
    assert any(outcome == "held up" for outcome, _ in events)
    passed = [time for outcome, time in events if outcome == "passed"]
    assert passed and math.isclose(passed[0], order_changed_at)  # it got ahead only through a logged pass
    assert race.standings()[0] is grid[1]


def test_controlled_car_pits_finishes_and_slows_under_a_vsc():
    plan = Strategy(TyreCompound.MEDIUM, 20.0, (PitStop(2, TyreCompound.SOFT),))
    times = {}
    for vsc in (False, True):
        car = RaceCar(1, "A", FAST, plan, control=CarControl())
        control = RaceControl([Incident(30.0, Flag.VSC, 30.0)] if vsc else [])
        race = Race(Stadium(), 4, [car], race_control=control, traffic=None)
        race.run(0.1)
        assert car.laps == 4 and car.finish_time is not None
        assert [(stop.number, stop.lap) for stop in race.pit_events] == [(1, 2)]
        times[vsc] = car.finish_time
    assert times[True] > times[False] + 5  # 30 s at 1/1.4 of the target speed costs well over 5 s


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
