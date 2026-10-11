import math

from abstract_classes import CarSpecification

G = 9.81
AIR_DENSITY = 1.225
TYRE_GRIP = 1.8


def aero(area: float, v: float) -> float:
    return 0.5 * AIR_DENSITY * area * v * v


def corner_speed(spec: CarSpecification, radius: float, tyre_grip: float = TYRE_GRIP) -> float:
    k = tyre_grip * 0.5 * AIR_DENSITY * spec.downforce
    if spec.mass / radius <= k:
        return math.inf
    return math.sqrt(tyre_grip * spec.mass * G / (spec.mass / radius - k))


def longitudinal_grip(spec: CarSpecification, v: float, radius: float, tyre_grip: float = TYRE_GRIP) -> float:
    grip = tyre_grip * (spec.mass * G + aero(spec.downforce, v))
    centrifugal = spec.mass * v * v / radius
    return math.sqrt(max(grip ** 2 - centrifugal ** 2, 0.0))


def acceleration(spec: CarSpecification, v: float, radius: float, gradient: float, tyre_grip: float = TYRE_GRIP) -> float:
    drive = min(spec.power / max(v, 1.0), longitudinal_grip(spec, v, radius, tyre_grip))
    return (drive - aero(spec.drag, v)) / spec.mass - G * gradient / 100


def deceleration(spec: CarSpecification, v: float, radius: float, gradient: float, tyre_grip: float = TYRE_GRIP) -> float:
    return (longitudinal_grip(spec, v, radius, tyre_grip) + aero(spec.drag, v)) / spec.mass - G * gradient / 100
