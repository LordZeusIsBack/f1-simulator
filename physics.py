import math

from abstract_classes import CarSpecification

G = 9.81
AIR_DENSITY = 1.225
TYRE_GRIP = 1.8


def aero(area: float, v: float) -> float:
    return 0.5 * AIR_DENSITY * area * v * v


def _tilt(banking: float) -> tuple[float, float]:
    """cos and sin of the banking angle (degrees); exactly (1, 0) when flat, so flat results match V0 to the bit."""
    if banking == 0:
        return 1.0, 0.0
    angle = math.radians(banking)
    return math.cos(angle), math.sin(angle)


def corner_speed(spec: CarSpecification, radius: float, tyre_grip: float = TYRE_GRIP, banking: float = 0.0) -> float:
    """Highest steady speed on this radius. On a banked road the normal force carries part of the centripetal force:
    m v^2/r cos(b) - m g sin(b) <= grip (m g cos(b) + m v^2/r sin(b) + downforce)."""
    cos, sin = _tilt(banking)
    k = tyre_grip * 0.5 * AIR_DENSITY * spec.downforce
    denominator = spec.mass / radius * (cos - tyre_grip * sin) - k
    if denominator <= 0:
        return math.inf
    return math.sqrt((tyre_grip * cos + sin) * spec.mass * G / denominator)


def longitudinal_grip(spec: CarSpecification, v: float, radius: float, tyre_grip: float = TYRE_GRIP,
                      banking: float = 0.0) -> float:
    """N of grip left for driving or braking once the corner's lateral force is taken (friction circle)."""
    cos, sin = _tilt(banking)
    centrifugal = spec.mass * v * v / radius
    grip = tyre_grip * (spec.mass * G * cos + centrifugal * sin + aero(spec.downforce, v))
    lateral = centrifugal * cos - spec.mass * G * sin
    return math.sqrt(max(grip ** 2 - lateral ** 2, 0.0))


def acceleration(spec: CarSpecification, v: float, radius: float, gradient: float, tyre_grip: float = TYRE_GRIP,
                 banking: float = 0.0) -> float:
    drive = min(spec.power / max(v, 1.0), longitudinal_grip(spec, v, radius, tyre_grip, banking))
    return (drive - aero(spec.drag, v)) / spec.mass - G * gradient / 100


def deceleration(spec: CarSpecification, v: float, radius: float, gradient: float, tyre_grip: float = TYRE_GRIP,
                 banking: float = 0.0) -> float:
    return (longitudinal_grip(spec, v, radius, tyre_grip, banking) + aero(spec.drag, v)) / spec.mass - G * gradient / 100
