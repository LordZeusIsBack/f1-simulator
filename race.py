from bisect import bisect_right
from dataclasses import dataclass

from abstract_classes import Car, Track
from simulation import simulate_lap, track_points

GRID_SPACING = 8.0  # m between consecutive grid slots, model assumption


@dataclass
class RaceCar:
    """One car in one race. `car` is the (shareable) configuration; the other fields are this car's own state."""
    number: int
    team: str
    car: Car
    distance: float = 0.0  # m since the start line, negative while still behind it on the grid
    finish_time: float | None = None  # s of race time at which the car completed the race distance


class LapProfile:
    """The V0 flying-lap speed profile turned into a distance <-> time lookup, repeated lap after lap."""

    def __init__(self, car: Car, track: Track):
        _, speed = simulate_lap(car, track)
        self.distance, self.time = [0.0], [0.0]  # m and s at each track point; the last entry closes the lap
        for i, (ds, _, _) in enumerate(track_points(track)):
            self.distance.append(self.distance[-1] + ds)
            # same trapezoid as simulate_lap's lap time: average of the speeds at both ends of ds
            self.time.append(self.time[-1] + 2 * ds / (speed[i] + speed[(i + 1) % len(speed)]))

    def time_at(self, distance: float) -> float:
        """s from the start line to `distance` m (any lap, may be negative)."""
        laps, rest = divmod(distance, self.distance[-1])
        return laps * self.time[-1] + _interpolate(rest, self.distance, self.time)

    def distance_at(self, time: float) -> float:
        """Inverse of time_at: m covered from the start line after `time` s."""
        laps, rest = divmod(time, self.time[-1])
        return laps * self.distance[-1] + _interpolate(rest, self.time, self.distance)


def _interpolate(x: float, xs: list[float], ys: list[float]) -> float:
    i = min(bisect_right(xs, x), len(xs) - 1)  # xs[i - 1] <= x < xs[i]
    return ys[i - 1] + (x - xs[i - 1]) / (xs[i] - xs[i - 1]) * (ys[i] - ys[i - 1])


class Race:
    """Race state: the track, the lap count, the cars in grid order and the elapsed race time."""

    def __init__(self, track: Track, laps: int, grid: list[RaceCar]):
        if not isinstance(laps, int) or laps < 1:
            raise ValueError(f"laps must be a positive integer, got {laps!r}")
        if not grid:
            raise ValueError("a race needs at least one car")
        if len({car.number for car in grid}) != len(grid):
            raise ValueError("car numbers must be unique")
        self.track = track
        self.laps = laps
        self.cars = grid
        self.time = 0.0  # s since the start
        self.race_distance = laps * track.length  # m
        self._profiles = {car.number: LapProfile(car.car, track) for car in grid}
        for slot, car in enumerate(grid):
            car.distance = -slot * GRID_SPACING
            car.finish_time = None

    @property
    def finished(self) -> bool:
        return all(car.finish_time is not None for car in self.cars)

    def laps_completed(self, car: RaceCar) -> int:
        if car.finish_time is not None:
            return self.laps
        return max(0, int(car.distance // self.track.length))

    def step(self, dt: float) -> None:
        """Move every running car `dt` s further along its own lap profile."""
        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt!r}")
        for car in self.cars:
            if car.finish_time is not None:
                continue
            profile = self._profiles[car.number]
            start = profile.time_at(car.distance)
            car.distance = profile.distance_at(start + dt)
            if car.distance >= self.race_distance:
                # exact crossing time inside this step, so results don't depend on dt
                car.finish_time = self.time + profile.time_at(self.race_distance) - start
                car.distance = self.race_distance
        self.time += dt

    def run(self, dt: float = 0.5) -> list[RaceCar]:
        while not self.finished:
            self.step(dt)
        return self.standings()

    def standings(self) -> list[RaceCar]:
        """Finished cars by finish time, then running cars by distance. Ties keep grid order."""
        return sorted(
            self.cars,
            key=lambda car: (0, car.finish_time) if car.finish_time is not None else (1, -car.distance),
        )
