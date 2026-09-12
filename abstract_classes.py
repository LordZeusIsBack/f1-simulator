from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum


@dataclass
class CarSpecification:
    power: float
    drag: float
    downforce: float


@dataclass
class TrackSegment:
    length: float
    radius: float
    gradient: float


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



class Straight(TrackSegment):
    pass



class Corner(TrackSegment):
    pass



class Car:
    def __init__(self, specification: CarSpecification):
        self.specification = specification


class TyreCompound(Enum):
    SOFT = "soft"
    MEDIUM = "medium"
    HARD = "hard"
    INTERMEDIATE = "intermediate"
    WET = "wet"
