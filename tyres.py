from dataclasses import dataclass
from typing import NamedTuple

from abstract_classes import TyreCompound
from physics import TYRE_GRIP

WORN_GRIP_LOSS = 0.06  # fraction of a compound's grip lost at 100 % wear, placeholder


class Compound(NamedTuple):
    grip: float  # friction coefficient of a new tyre on a dry track (dimensionless), placeholder
    wear_per_lap: float  # fraction of the tyre's life used per lap, placeholder
    wet_loss: float = 0.0  # fraction of grip lost on a fully wet track (wetness 1), placeholder


# Placeholder model values, not Pirelli data. A new medium on a dry track matches V0's single grip value.
# Slicks lose most grip in the wet; intermediates and wets start lower but lose less.
DRY_COMPOUNDS = {
    TyreCompound.SOFT: Compound(grip=1.83, wear_per_lap=0.05, wet_loss=0.65),
    TyreCompound.MEDIUM: Compound(grip=TYRE_GRIP, wear_per_lap=0.03, wet_loss=0.65),
    TyreCompound.HARD: Compound(grip=1.775, wear_per_lap=0.02, wet_loss=0.65),
}
COMPOUNDS = {
    **DRY_COMPOUNDS,
    TyreCompound.INTERMEDIATE: Compound(grip=1.55, wear_per_lap=0.03, wet_loss=0.32),
    TyreCompound.WET: Compound(grip=1.35, wear_per_lap=0.03, wet_loss=0.15),
}


@dataclass(frozen=True)
class Tyres:
    """The set fitted to a car: its compound and how many laps it has done."""
    compound: TyreCompound
    laps: int = 0

    def wear(self, compounds: dict[TyreCompound, Compound] = COMPOUNDS) -> float:
        """0 = new, 1 = fully worn. Linear in laps, then stays at 1 (no failure model)."""
        return min(1.0, self.laps * compounds[self.compound].wear_per_lap)

    def grip(self, compounds: dict[TyreCompound, Compound] = COMPOUNDS, wetness: float = 0.0) -> float:
        compound = compounds[self.compound]
        return compound.grip * (1 - WORN_GRIP_LOSS * self.wear(compounds)) * (1 - compound.wet_loss * wetness)


def best_compound(compounds: dict[TyreCompound, Compound], wetness: float) -> TyreCompound:
    """The compound with the most grip as a new set at this wetness (first in table order on a tie)."""
    return max(compounds, key=lambda compound: Tyres(compound).grip(compounds, wetness))
