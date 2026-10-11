import math

from abstract_classes import CarSpecification

G = 9.81
AIR_DENSITY = 1.225
TYRE_GRIP = 1.8


def aero(area: float, v: float) -> float:
    return 0.5 * AIR_DENSITY * area * v * v


def corner_speed(spec: CarSpecification, radius: float) -> float:
    k = TYRE_GRIP * 0.5 * AIR_DENSITY * spec.downforce
    if spec.mass / radius <= k:
        return math.inf
    return math.sqrt(TYRE_GRIP * spec.mass * G / (spec.mass / radius - k))


def longitudinal_grip(spec: CarSpecification, v: float, radius: float) -> float:
    grip = TYRE_GRIP * (spec.mass * G + aero(spec.downforce, v))
    centrifugal = spec.mass * v * v / radius
    return math.sqrt(max(grip ** 2 - centrifugal ** 2, 0.0))


def acceleration(spec: CarSpecification, v: float, radius: float, gradient: float) -> float:
    drive = min(spec.power / max(v, 1.0), longitudinal_grip(spec, v, radius))
    return (drive - aero(spec.drag, v)) / spec.mass - G * gradient / 100


def deceleration(spec: CarSpecification, v: float, radius: float, gradient: float) -> float:
    return (longitudinal_grip(spec, v, radius) + aero(spec.drag, v)) / spec.mass - G * gradient / 100
