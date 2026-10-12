from dataclasses import dataclass

from abstract_classes import TyreCompound
from tyres import COMPOUNDS, Compound, Tyres, best_compound

WEATHER_MARGIN = 0.05  # a weather stop needs a new set this much grippier than the current compound, placeholder


@dataclass(frozen=True)
class PitStop:
    """One planned stop, made as the car completes lap `lap`."""
    lap: int
    compound: TyreCompound | None = None  # new set to fit; None keeps the current tyres
    fuel: float = 0.0  # kg to add


@dataclass(frozen=True)
class Strategy:
    """A fixed plan: starting tyres and fuel, then stops at set laps. It decides; the race applies the rules.

    With react_to_weather, the car also pits whenever another compound suits the current wetness clearly better."""
    compound: TyreCompound
    fuel: float  # kg on board at the start
    stops: tuple[PitStop, ...] = ()
    name: str = ""
    react_to_weather: bool = False

    def planned_stop(self, lap: int) -> PitStop | None:
        return next((stop for stop in self.stops if stop.lap == lap), None)

    def stop_after(
        self,
        lap: int,
        tyres: Tyres,
        wetness: float = 0.0,
        compounds: dict[TyreCompound, Compound] = COMPOUNDS,
    ) -> PitStop | None:
        """The planned stop for this lap if there is one, else a weather stop if the plan reacts to weather."""
        planned = self.planned_stop(lap)
        if planned or not self.react_to_weather:
            return planned
        best = best_compound(compounds, wetness)
        current = Tyres(tyres.compound).grip(compounds, wetness)  # new-set grip: compare compounds, not wear
        if Tyres(best).grip(compounds, wetness) > current * (1 + WEATHER_MARGIN):
            return PitStop(lap, best)
        return None
