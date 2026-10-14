"""Driver control of the car's motion (P2-V3): pedals, the physics that executes them, and a speed controller.

Three levels, kept apart:
1. tactical: a P2-V2 driving policy picks a DriverAction (driving.py);
2. controller: STYLES turns the action into a share of the tyre grip to use, BrakingEnvelope gives the highest speed
   at each point from which the car can still make the corners ahead, and track_speed picks the pedals;
3. physics: step_motion integrates the pedals (speed is state; distance follows from it).
Longitudinal only: no lateral position, racing line or lane geometry is modelled.
"""
import math
from bisect import bisect_right
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import accumulate

from abstract_classes import Car, CarSpecification, Track
from driving import DriverAction
from physics import G, aero, corner_speed, longitudinal_grip
from simulation import track_points

CONTROL_STEP = 0.02  # s, default physics sub-step (≈ 1.8 m at 90 m/s, about the 1 m track resolution)
MAX_CONTROL_STEP = 0.05  # s, largest sub-step allowed (≈ 4.5 m at 90 m/s): beyond it braking points smear
CLIP_TOLERANCE = 1e-6  # m/s over a corner's limit before CarControl.clipped counts it (ignores float rounding)

# Share of the tyre grip the controller plans to use, per tactical action. Placeholders, not data.
STYLES = {
    DriverAction.ATTACK: 1.0,  # at the limit
    DriverAction.DEFEND: 1.0,  # no lateral model: defending = pushing at the limit to keep the gap
    DriverAction.MAINTAIN_PACE: 0.97,  # a margin kept over a race distance
    DriverAction.CONSERVE_TYRES: 0.90,  # slower; tyre wear does not depend on it yet
}


@dataclass(frozen=True)
class Control:
    """Pedal demands for one sub-step, each 0-1. Throttle and brake are not pressed together."""
    throttle: float = 0.0
    brake: float = 0.0

    def __post_init__(self):
        for name in ("throttle", "brake"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:  # NaN fails too
                raise ValueError(f"{name} must be a number from 0 to 1, got {value!r}")
        if self.throttle > 0 and self.brake > 0:
            raise ValueError("throttle and brake cannot both be pressed")


COAST, FULL_THROTTLE, FULL_BRAKE = Control(), Control(throttle=1.0), Control(brake=1.0)


@dataclass
class CarControl:
    """Opts a RaceCar into the control model and holds its state: RaceCar(..., control=CarControl())."""
    action: DriverAction = DriverAction.MAINTAIN_PACE  # what the controller carries out; driving.run updates it
    speed: float = 0.0  # m/s, set by Race at the start, then integrated
    clipped: int = 0  # sub-steps in which the corner's grip limit capped the speed (0 for a well-driven car)


def acceleration(spec: CarSpecification, v: float, radius: float, gradient: float, tyre_grip: float, banking: float,
                 control: Control) -> float:
    """m/s² along the track. Same forces as physics.acceleration, with each pedal scaling its force:
    drive = throttle × min(power / v, grip left), braking = brake × grip left, minus drag and gravity."""
    grip = longitudinal_grip(spec, v, radius, tyre_grip, banking)
    drive = control.throttle * min(spec.power / max(v, 1.0), grip)
    return (drive - control.brake * grip - aero(spec.drag, v)) / spec.mass - G * gradient / 100


def step_motion(spec: CarSpecification, v: float, point: tuple, tyre_grip: float, control: Control,
                h: float) -> tuple[float, float]:
    """Integrate one sub-step of h s at a track point (ds, radius, gradient, banking): (new speed, metres covered).
    Explicit Euler on speed, floored at 0 (no reversing); trapezoid on distance."""
    if not 0 < h <= MAX_CONTROL_STEP:
        raise ValueError(f"sub-step must be in (0, {MAX_CONTROL_STEP}] s, got {h!r}")
    if not 0 <= v < math.inf:
        raise ValueError(f"speed must be finite and >= 0, got {v!r}")
    _, radius, gradient, banking = point
    v_new = max(0.0, v + acceleration(spec, v, radius, gradient, tyre_grip, banking, control) * h)
    return v_new, (v + v_new) / 2 * h


def track_speed(spec: CarSpecification, v: float, target: float, point: tuple, tyre_grip: float, h: float) -> Control:
    """The pedals that bring the speed closest to `target` after h s. Acceleration is linear in each pedal, so the
    demand is (needed − coasting) / (full pedal − coasting), clipped to 0-1."""
    _, radius, gradient, banking = point
    coast = acceleration(spec, v, radius, gradient, tyre_grip, banking, COAST)
    needed = (target - v) / h
    if needed >= coast:
        span = acceleration(spec, v, radius, gradient, tyre_grip, banking, FULL_THROTTLE) - coast
        return Control(throttle=min(1.0, (needed - coast) / span)) if span > 0 else COAST
    span = coast - acceleration(spec, v, radius, gradient, tyre_grip, banking, FULL_BRAKE)
    return Control(brake=min(1.0, (coast - needed) / span)) if span > 0 else COAST


class BrakingEnvelope:
    """Look-ahead for the controller: the highest speed at each track point from which the car can still slow for
    every corner ahead, braking with `tyre_grip`. A backward pass of acceleration() at full brake (gravity counted
    with the physically correct sign) around two laps, so the lap wraps."""

    def __init__(self, car: Car, track: Track, tyre_grip: float, fuel: float):
        spec = replace(car.specification, mass=car.specification.mass + fuel)
        self.points = track_points(track)
        self.distance = list(accumulate((point[0] for point in self.points), initial=0.0))  # m at each point
        self.speed = [corner_speed(spec, radius, tyre_grip, banking) for _, radius, _, banking in self.points]
        n = len(self.points)
        v = 1000.0  # m/s, far above any limit: going backwards, the first corner met sets the real value
        for k in reversed(range(2 * n)):
            i = k % n
            ds, radius, gradient, banking = self.points[i]
            entry = first = self._entry(spec, v, v, ds, radius, gradient, tyre_grip, banking, self.speed[i])
            entry = min(first, self._entry(spec, first, v, ds, radius, gradient, tyre_grip, banking, self.speed[i]))
            v = self.speed[i] = entry

    @staticmethod
    def _entry(spec, guess, v, ds, radius, gradient, tyre_grip, banking, limit):
        """Highest speed ds before a point reached at v, braking with the grip left at `guess`, capped at `limit`."""
        braking = -acceleration(spec, guess, radius, gradient, tyre_grip, banking, FULL_BRAKE)
        return min(limit, math.sqrt(max(v * v + 2 * braking * ds, 0.0)))

    def _index(self, lap_distance: float) -> int:
        return min(max(bisect_right(self.distance, lap_distance) - 1, 0), len(self.points) - 1)

    def point(self, lap_distance: float) -> tuple:
        """(ds, radius, gradient, banking) of the track point at this distance from the line."""
        return self.points[self._index(lap_distance)]

    def target(self, lap_distance: float) -> float:
        """m/s the car may do here: the lower of the two points around it, so no braking point is missed."""
        i = self._index(lap_distance)
        return min(self.speed[i], self.speed[(i + 1) % len(self.speed)])


# ponytail: keyed by object identity like race.lap_profile; ~0.2 MB per Monza envelope.
@lru_cache(maxsize=64)
def braking_envelope(car: Car, track: Track, tyre_grip: float, fuel: float) -> BrakingEnvelope:
    return BrakingEnvelope(car, track, tyre_grip, fuel)
