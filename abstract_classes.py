from dataclasses import dataclass
from abc import ABC, abstractmethod


class Track(ABC):
    def __init__(self):
        self.segments = []
        self.build_track()

    @abstractmethod
    def build_track(self):
        pass

    @property
    def name(self):
        return self.__class__.__name__



@dataclass
class TrackSegment:
    length: float
    radius: float
    elevation: float
    grip: float



class Straight(TrackSegment):
    pass



class Corner(TrackSegment):
    pass
