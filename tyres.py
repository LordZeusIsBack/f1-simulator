from dataclasses import dataclass
from typing import NamedTuple

from abstract_classes import TyreCompound
from physics import TYRE_GRIP

WORN_GRIP_LOSS = 0.06  # fraction of a compound's grip lost at 100 % wear, placeholder


class Compound(NamedTuple):
    grip: float  # friction coefficient of a new tyre (dimensionless), placeholder
    wear_per_lap: float  # fraction of the tyre's life used per lap, placeholder


# Placeholder model values, not Pirelli data. A new medium matches V0's single grip value.
# Wet-weather compounds are left out until weather exists (V4).
COMPOUNDS = {
    TyreCompound.SOFT: Compound(grip=1.83, wear_per_lap=0.05),
    TyreCompound.MEDIUM: Compound(grip=TYRE_GRIP, wear_per_lap=0.03),
    TyreCompound.HARD: Compound(grip=1.775, wear_per_lap=0.02),
}


@dataclass(frozen=True)
class Tyres:
    """The set fitted to a car: its compound and how many laps it has done."""
    compound: TyreCompound
    laps: int = 0

    def wear(self, compounds: dict[TyreCompound, Compound] = COMPOUNDS) -> float:
        """0 = new, 1 = fully worn. Linear in laps, then stays at 1 (no failure model)."""
        return min(1.0, self.laps * compounds[self.compound].wear_per_lap)

    def grip(self, compounds: dict[TyreCompound, Compound] = COMPOUNDS) -> float:
        return compounds[self.compound].grip * (1 - WORN_GRIP_LOSS * self.wear(compounds))
