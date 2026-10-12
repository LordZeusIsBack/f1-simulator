import math
from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum


@dataclass
class CarSpecification:
    power: float
    drag: float
    downforce: float
    mass: float = 800


@dataclass
class TrackSegment:
    length: float  # m
    radius: float  # m, math.inf on a straight; the tightest radius if it varies along the segment
    gradient: float  # %, positive uphill
    banking: float = 0.0  # degrees, positive = road tilted into the turn, negative = off-camber

    def points(self, step: float) -> list[tuple[float, float, float, float]]:
        """The ~step-long pieces the lap model drives: (length, radius, gradient, banking) of each."""
        n = max(1, round(self.length / step))
        return [(self.length / n, self.radius, self.gradient, self.banking)] * n


class Track(ABC):
    def __init__(self):
        self.segments: list[TrackSegment] = []
        self.build_track()

    @abstractmethod
    def build_track(self):
        pass

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def length(self):
        return sum(segment.length for segment in self.segments)



class Straight(TrackSegment):
    pass



class Corner(TrackSegment):
    pass


class Hairpin(Corner):
    """A turn of about 180 degrees (170-185 in F1-Encyclopedia's taxonomy). Its length follows from radius and angle."""

    def __init__(self, radius: float, gradient: float = 0.0, angle: float = 180.0, banking: float = 0.0):
        super().__init__(math.radians(angle) * radius, radius, gradient, banking)
        self.angle = angle  # degrees


class Spiral(Corner):
    """A decreasing- or increasing-radius corner (e.g. Parabolica). Curvature (1 / radius) changes linearly along it,
    as on an Euler spiral, so an infinite radius at one end makes a transition from a straight."""

    def __init__(self, length: float, entry_radius: float, exit_radius: float, gradient: float = 0.0,
                 banking: float = 0.0):
        super().__init__(length, min(entry_radius, exit_radius), gradient, banking)
        self.entry_radius, self.exit_radius = entry_radius, exit_radius

    def points(self, step):
        n = max(1, round(self.length / step))
        start, end = 1 / self.entry_radius, 1 / self.exit_radius
        curvatures = (start + (end - start) * (i + 0.5) / n for i in range(n))  # at the middle of each piece
        return [(self.length / n, 1 / k if k > 0 else math.inf, self.gradient, self.banking) for k in curvatures]


class Chicane(TrackSegment):
    """Corners in quick succession, usually in alternating directions. The lap model drives each part in turn (direction
    does not matter in a one-dimensional model). One segment for race control and traffic: never a straight."""

    def __init__(self, *parts: TrackSegment):
        if len(parts) < 2:
            raise ValueError("a chicane needs at least two parts")
        length = sum(part.length for part in parts)
        super().__init__(length, min(part.radius for part in parts),
                         sum(part.gradient * part.length for part in parts) / length)
        self.parts = parts

    def points(self, step):
        return [point for part in self.parts for point in part.points(step)]


class Esses(Chicane):
    """A flowing sequence of opposite-direction corners without a straight between them (Maggotts-Becketts, Suzuka's S)."""



class Car:
    def __init__(self, specification: CarSpecification):
        self.specification = specification


class TyreCompound(Enum):
    SOFT = "soft"
    MEDIUM = "medium"
    HARD = "hard"
    INTERMEDIATE = "intermediate"
    WET = "wet"
