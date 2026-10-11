from dataclasses import dataclass

from abstract_classes import TyreCompound


@dataclass(frozen=True)
class PitStop:
    """One planned stop, made as the car completes lap `lap`."""
    lap: int
    compound: TyreCompound | None = None  # new set to fit; None keeps the current tyres
    fuel: float = 0.0  # kg to add


@dataclass(frozen=True)
class Strategy:
    """A fixed plan: starting tyres and fuel, then stops at set laps. It decides; the race applies the rules."""
    compound: TyreCompound
    fuel: float  # kg on board at the start
    stops: tuple[PitStop, ...] = ()
    name: str = ""

    def stop_after(self, lap: int) -> PitStop | None:
        return next((stop for stop in self.stops if stop.lap == lap), None)
