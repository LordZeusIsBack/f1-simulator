import math
from bisect import bisect_right
from dataclasses import dataclass

AIR_TEMP_RANGE = (-10.0, 50.0)  # °C accepted in a timeline
MAX_RAIN = 50.0  # mm/h accepted in a timeline
SUN_HEATING = 15.0  # °C a fully dry track sits above the air; a fully wet one is at air temperature, placeholder
WETTING_RATE = 0.001  # 1/s per mm/h of rain, placeholder
DRYING_RATE = 3e-5  # 1/s per °C of track temperature above DRYING_MIN_TEMP, placeholder
DRYING_MIN_TEMP = 0.0  # °C, no drying at or below this track temperature


@dataclass(frozen=True)
class WeatherPoint:
    """One keyframe of a scripted timeline. Values between keyframes are interpolated linearly."""
    time: float  # s of race time
    air_temp: float  # °C
    rain: float = 0.0  # mm/h

    def __post_init__(self):
        if not self.time >= 0:
            raise ValueError(f"time must be >= 0 s, got {self.time!r}")
        if not AIR_TEMP_RANGE[0] <= self.air_temp <= AIR_TEMP_RANGE[1]:
            raise ValueError(f"air_temp must be {AIR_TEMP_RANGE[0]}-{AIR_TEMP_RANGE[1]} °C, got {self.air_temp!r}")
        if not 0 <= self.rain <= MAX_RAIN:
            raise ValueError(f"rain must be 0-{MAX_RAIN} mm/h, got {self.rain!r}")


@dataclass(frozen=True)
class Conditions:
    """Weather and track state at one moment."""
    time: float  # s of race time
    air_temp: float  # °C
    track_temp: float  # °C, air_temp + SUN_HEATING × (1 − wetness)
    rain: float  # mm/h
    wetness: float  # 0 = dry, 1 = fully wet (standing water)


class Weather:
    """A scripted timeline (air temperature, rain) plus the track wetness it produces over time."""

    def __init__(self, timeline: list[WeatherPoint], wetness: float = 0.0):
        if not timeline:
            raise ValueError("a weather timeline needs at least one point")
        if any(b.time <= a.time for a, b in zip(timeline, timeline[1:])):
            raise ValueError("timeline points must be in strictly increasing time order")
        if not 0 <= wetness <= 1:
            raise ValueError(f"wetness must be 0-1, got {wetness!r}")
        self.timeline = list(timeline)
        self.time = 0.0  # s
        self.wetness = float(wetness)

    def _scripted(self, time: float) -> tuple[float, float]:
        """(air °C, rain mm/h) at `time`: held before the first and after the last point, linear in between."""
        points = self.timeline
        i = bisect_right([point.time for point in points], time)
        if i == 0:
            return points[0].air_temp, points[0].rain
        if i == len(points):
            return points[-1].air_temp, points[-1].rain
        a, b = points[i - 1], points[i]
        fraction = (time - a.time) / (b.time - a.time)
        return a.air_temp + fraction * (b.air_temp - a.air_temp), a.rain + fraction * (b.rain - a.rain)

    @property
    def conditions(self) -> Conditions:
        air, rain = self._scripted(self.time)
        return Conditions(self.time, air, air + SUN_HEATING * (1 - self.wetness), rain, self.wetness)

    def advance(self, dt: float) -> Conditions:
        """Move `dt` s on. Wetness follows dW/dt = k_wet (1 − W) − k_dry W with rates frozen at the step start."""
        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt!r}")
        now = self.conditions
        k_wet = WETTING_RATE * now.rain
        k_dry = DRYING_RATE * max(0.0, now.track_temp - DRYING_MIN_TEMP)
        if k_wet + k_dry > 0:  # exact solution for constant rates: relax towards the balance point
            balance = k_wet / (k_wet + k_dry)
            self.wetness = balance + (self.wetness - balance) * math.exp(-(k_wet + k_dry) * dt)
        self.time += dt
        return self.conditions
