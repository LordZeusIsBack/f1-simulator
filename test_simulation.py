import math

from abstract_classes import Car, CarSpecification, Corner, Straight, Track
from cars import CARS
from physics import G, corner_speed
from simulation import simulate_lap
from tracks import MonzaV0


class Stadium(Track):
    def build_track(self):
        self.segments = [Straight(500, math.inf, 0), Corner(50 * math.pi, 50, 0)] * 2


def test_car_brakes_down_to_grip_limit():
    car = Car(CarSpecification(power=750_000, drag=1.2, downforce=3.5))
    _, speed = simulate_lap(car, Stadium())
    assert math.isclose(min(speed), corner_speed(car.specification, 50), rel_tol=0.01)
    assert all((a * a - b * b) / 2 < 10 * G for a, b in zip(speed, speed[1:]))  # no 10 g stops


def test_monza_v0_lap_times_unchanged_from_v0():
    # recorded from V0 (commit 76f1562): a regression guard, not a validation against real F1
    v0 = {"Red Bull": 94.55456328563695, "Ferrari": 95.19614020957577,
          "McLaren": 93.9983425811837, "Mercedes": 95.290917425722}
    for team, car in CARS.items():
        assert math.isclose(simulate_lap(car, MonzaV0())[0], v0[team], rel_tol=1e-12)


if __name__ == "__main__":
    test_car_brakes_down_to_grip_limit()
    test_monza_v0_lap_times_unchanged_from_v0()
    print("ok")
