import math
from unittest import TestCase

from abstract_classes import CarSpecification, Chicane, Corner, Esses, Hairpin, Spiral, Straight, Track
from cars import CARS
from physics import G, corner_speed, longitudinal_grip
from simulation import STEP, simulate_lap, track_points
from tracks import CIRCUITS, LATERAL_G, Circuit, Monaco, Zandvoort, radius_for, spiral, straight, turn
from traffic import is_straight

assert_raises = TestCase().assertRaises
SPEC = CarSpecification(power=750_000, drag=1.2, downforce=3.5)


class Loop(Track):
    def __init__(self, *segments):
        self.parts = segments
        super().__init__()

    def build_track(self):
        self.segments = list(self.parts)


def test_hairpin_spiral_and_chicane_geometry():
    hairpin = Hairpin(12.0, angle=180)
    assert math.isclose(hairpin.length, math.pi * 12.0) and hairpin.radius == 12.0 and not is_straight(hairpin)
    assert math.isclose(Hairpin(10.0, angle=90).length, 5 * math.pi)

    tightening = Spiral(100.0, 200.0, 50.0)
    points = tightening.points(STEP)
    curvatures = [1 / radius for _, radius, _, _ in points]
    assert len(points) == 100 and math.isclose(sum(ds for ds, *_ in points), 100.0)
    assert all(b > a for a, b in zip(curvatures, curvatures[1:])) and 50.0 < points[-1][1] < points[0][1] < 200.0
    steps = [b - a for a, b in zip(curvatures, curvatures[1:])]
    assert max(steps) - min(steps) < 1e-12  # curvature linear in distance (an Euler spiral)
    assert tightening.radius == 50.0 and not is_straight(tightening)
    transition = Spiral(50.0, math.inf, 40.0).points(STEP)  # from a straight into a corner
    assert transition[0][1] > 1000 and math.isclose(1 / transition[-1][1], (1 / 40) * 49.5 / 50)

    parts = (Corner(30.0, 20.0, 1.0), Straight(10.0, math.inf, 0.0), Corner(40.0, 25.0, -1.0))
    chicane = Chicane(*parts)
    assert chicane.length == 80.0 and chicane.radius == 20.0 and not is_straight(chicane)
    assert math.isclose(chicane.gradient, (30 - 40) / 80)
    assert chicane.points(STEP) == [p for part in parts for p in part.points(STEP)]
    assert isinstance(Esses(*parts), Chicane)
    with assert_raises(ValueError):
        Chicane(Corner(30.0, 20.0, 0.0))


def test_plain_segments_cut_into_points_as_in_v0():
    segment = Corner(45.0, 14.0, 0.3)
    assert segment.points(STEP) == [(45.0 / 45, 14.0, 0.3, 0.0)] * 45
    track = Loop(Straight(500.4, math.inf, 0.0), Corner(0.2, 30.0, 0.0))
    assert len(track_points(track)) == 501  # every segment gets at least one point


def test_banking_raises_and_off_camber_lowers_the_cornering_limit():
    flat = corner_speed(SPEC, 50.0)
    k = 1.8 * 0.5 * 1.225 * SPEC.downforce  # V0's closed form
    assert flat == math.sqrt(1.8 * SPEC.mass * G / (SPEC.mass / 50.0 - k))
    assert corner_speed(SPEC, 50.0, banking=19.0) > flat > corner_speed(SPEC, 50.0, banking=-5.0)
    for banking in (-5.0, 0.0, 10.0, 19.0):  # at the limit speed, the friction circle has nothing left
        v = corner_speed(SPEC, 50.0, banking=banking)
        assert longitudinal_grip(SPEC, v, 50.0, banking=banking) < 1e-3 * SPEC.mass * G
    assert corner_speed(SPEC, 50.0, banking=45.0) == math.inf  # steep enough: no grip limit (grip 1.8 > cot 45)
    flat_track, banked_track = Loop(straight(400), turn(160, 180)), Loop(straight(400), turn(160, 180, banking=18))
    assert simulate_lap(CARS["McLaren"], banked_track)[0] < simulate_lap(CARS["McLaren"], flat_track)[0]


def test_radius_follows_the_encyclopedia_lateral_g_table():
    for speed, g in LATERAL_G:
        assert math.isclose(radius_for(speed), (speed / 3.6) ** 2 / (g * G))
    assert math.isclose(radius_for(30.0), (30 / 3.6) ** 2 / (2.0 * G))  # held at the slowest class
    assert math.isclose(radius_for(340.0), (340 / 3.6) ** 2 / (5.75 * G))  # and the fastest
    radii = [radius_for(speed) for speed in range(40, 360, 5)]
    assert all(b > a for a, b in zip(radii, radii[1:]))
    assert math.isclose(spiral(100, 100, 90).length, math.radians(90) * radius_for(100))  # equal ends: an arc


def test_every_circuit_is_complete_and_drivable():
    assert len(CIRCUITS) == 28 and all(issubclass(c, Circuit) for c in CIRCUITS.values())
    for name, circuit in CIRCUITS.items():
        track = circuit()
        assert math.isclose(track.length, circuit.official_length, rel_tol=1e-9), name
        assert abs(sum(s.gradient * s.length / 100 for s in track.segments)) < 1e-6, name  # a lap climbs as much as it falls
        assert 0.85 < track.straight_scale < 1.6, name  # estimated straights within reason of the official length
        if name != "Monaco":  # Grand Prix distance: the fewest laps over 305 km (Monaco is the exception)
            assert track.laps * track.length > 305_000 > (track.laps - 1) * track.length, name
        assert 0 <= circuit.rain_chance <= 1 and 0 <= circuit.neutralisation_chance <= 1 and circuit.tyre_wear > 0
        lap, speed = simulate_lap(CARS["McLaren"], track)
        assert 50 < lap < 130 and min(speed) > 10 and max(speed) < 110, name
    assert Monaco().length < min(c.official_length for n, c in CIRCUITS.items() if n != "Monaco")
    assert [s.banking for s in Zandvoort().segments if s.banking] == [19, 18]


def test_a_layout_that_cannot_fit_its_length_is_rejected():
    class Tiny(Circuit):
        official_length, laps = 100.0, 3100

        def layout(self):
            return [straight(50), turn(100, 360)]

    with assert_raises(ValueError):
        Tiny()


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
