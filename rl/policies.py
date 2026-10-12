"""Policies map (observation, action_mask) -> action. They see only the observation, never the simulator."""
import random
from dataclasses import dataclass, fields

from abstract_classes import TyreCompound
from rl.env import COMPOUND_ORDER, Observation

STAY = 0
PIT = {compound: i + 1 for i, compound in enumerate(COMPOUND_ORDER)}  # TyreCompound -> action
INTER_FROM, WET_FROM = 0.40, 0.68  # wetness at which inters, then wets, grip best (V4 crossovers, rounded)


def current_compound(observation: Observation) -> TyreCompound:
    return next(c for c in COMPOUND_ORDER if getattr(observation, c.value) == 1.0)


def _allowed(action: int, mask) -> int:
    return action if mask[action] else STAY


def stay_out(observation: Observation, mask) -> int:
    """Never pits (and so breaks the two-compound rule): the floor any sensible policy must beat."""
    return STAY


@dataclass(frozen=True)
class FixedOneStop:
    """Pits once, for `compound`, at the first decision at or after `at` race progress. Ignores weather and flags."""
    at: float = 0.5
    compound: TyreCompound = TyreCompound.HARD

    def __call__(self, observation: Observation, mask) -> int:
        if observation.stops == 0 and observation.progress >= self.at:
            return _allowed(PIT[self.compound], mask)
        return STAY


@dataclass(frozen=True)
class RuleBased:
    """Hand-written strategist with four tunable thresholds (all race-progress or wear fractions)."""
    wear_limit: float = 0.75  # pit for fresh dry tyres at this wear
    neutral_from: float = 0.3  # take a cheap first stop under VSC/SC between these progress values
    neutral_to: float = 0.85
    final_call: float = 0.85  # if the two-compound rule is still unmet at this progress, pit now

    def __call__(self, observation: Observation, mask) -> int:
        fitted = current_compound(observation)
        dry_choice = TyreCompound.HARD if fitted is TyreCompound.MEDIUM else TyreCompound.MEDIUM
        needed = TyreCompound.WET if observation.wetness >= WET_FROM else (
            TyreCompound.INTERMEDIATE if observation.wetness >= INTER_FROM else None)
        on_wet_tyres = fitted in (TyreCompound.INTERMEDIATE, TyreCompound.WET)
        if needed is not None and fitted is not needed:
            return _allowed(PIT[needed], mask)
        if needed is None and on_wet_tyres and observation.wetness < INTER_FROM - 0.1:
            return _allowed(PIT[TyreCompound.MEDIUM], mask)  # back to slicks once clearly dry
        if on_wet_tyres:
            return STAY
        neutralised = observation.vsc or observation.safety_car
        if neutralised and observation.stops == 0 and self.neutral_from <= observation.progress <= self.neutral_to:
            return _allowed(PIT[dry_choice], mask)
        if observation.tyre_wear >= self.wear_limit:
            return _allowed(PIT[dry_choice], mask)
        if not observation.two_compounds and observation.progress >= self.final_call:
            return _allowed(PIT[dry_choice], mask)
        return STAY

    def as_vector(self) -> tuple[float, ...]:
        return tuple(getattr(self, f.name) for f in fields(self))


class RandomPolicy:
    """Stays out with probability 1 - pit_chance, else picks a random allowed pit action. Seeded."""

    def __init__(self, seed: int, pit_chance: float = 0.1):
        self.rng, self.pit_chance = random.Random(seed), pit_chance

    def __call__(self, observation: Observation, mask) -> int:
        pits = [action for action, ok in enumerate(mask) if ok and action != STAY]
        if pits and self.rng.random() < self.pit_chance:
            return self.rng.choice(pits)
        return STAY
