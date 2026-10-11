import math

from abstract_classes import Car, CarSpecification, Corner, Straight, Track
from physics import G, corner_speed
from simulation import simulate_lap


class Stadium(Track):
    def build_track(self):
        self.segments = [Straight(500, math.inf, 0), Corner(50 * math.pi, 50, 0)] * 2


def test_car_brakes_down_to_grip_limit():
    car = Car(CarSpecification(power=750_000, drag=1.2, downforce=3.5))
    _, speed = simulate_lap(car, Stadium())
    assert math.isclose(min(speed), corner_speed(car.specification, 50), rel_tol=0.01)
    assert all((a * a - b * b) / 2 < 10 * G for a, b in zip(speed, speed[1:]))  # no 10 g stops


if __name__ == "__main__":
    test_car_brakes_down_to_grip_limit()
    print("ok")
