import math
from dataclasses import dataclass
from enum import IntEnum


class Flag(IntEnum):
    """Track-wide race-control state, in rising order of severity."""
    GREEN = 0
    YELLOW = 1  # local: one track segment
    VSC = 2  # virtual safety car
    SAFETY_CAR = 3


# Every state can return to GREEN and may escalate; nothing de-escalates except to GREEN.
TRANSITIONS = {
    Flag.GREEN: {Flag.YELLOW, Flag.VSC, Flag.SAFETY_CAR},
    Flag.YELLOW: {Flag.GREEN, Flag.VSC, Flag.SAFETY_CAR},
    Flag.VSC: {Flag.GREEN, Flag.SAFETY_CAR},
    Flag.SAFETY_CAR: {Flag.GREEN},
}


def check_transition(old: Flag, new: Flag) -> None:
    if new not in TRANSITIONS[old]:
        raise ValueError(f"race control cannot go from {old.name} to {new.name}")


@dataclass(frozen=True)
class RaceControlRules:
    """Effects and penalties. Every value is a model assumption, not the FIA sporting regulations."""
    yellow_slowdown: float = 0.10  # extra time fraction for a car inside the yellow segment
    vsc_factor: float = 1.40  # under VSC every car laps 40 % slower than its own flying lap
    sc_factor: float = 1.60  # pace of the car leading the safety-car queue
    sc_catch_up_factor: float = 1.30  # pace of the others until they reach the queue
    sc_gap: float = 10.0  # m between cars in the safety-car queue
    drive_through_loss: float = 20.0  # s a drive-through costs
    two_compound_penalty: float = 30.0  # s for a finisher that used neither two dry compounds nor wet tyres; 0 = off
    drs_max_wetness: float = 0.3  # DRS is disabled on a track wetter than this


@dataclass(frozen=True)
class Incident:
    """A scripted incident: what race control calls, for how long, and which car (if any) retires."""
    time: float  # s of race time
    flag: Flag | None = None  # YELLOW, VSC or SAFETY_CAR; None = no flag (e.g. a car retires in the pits)
    duration: float = 0.0  # s the flag lasts; for SAFETY_CAR the minimum, then it ends as the leader crosses the line
    retire: int | None = None  # number of the car that stops for good
    segment: int | None = None  # yellow zone (track segment index); default: where the retiring car is
    reason: str = ""

    def __post_init__(self):
        if not self.time >= 0:
            raise ValueError(f"incident time must be >= 0 s, got {self.time!r}")
        if self.flag is Flag.GREEN:
            raise ValueError("an incident cannot call a green flag: flags clear by themselves")
        if self.flag is not None and not (0 < self.duration < math.inf):
            raise ValueError(f"a flag needs a finite duration > 0 s, got {self.duration!r}")
        if self.flag is None and self.retire is None:
            raise ValueError("an incident must call a flag or retire a car")
        if self.flag is Flag.YELLOW and self.retire is None and self.segment is None:
            raise ValueError("a yellow flag needs a segment or a retiring car to place it")


@dataclass(frozen=True)
class Penalty:
    """A scripted stewards' decision."""
    time: float  # s of race time when it is issued
    car: int
    kind: str = "time"  # "time" (added to the race time) or "drive-through" (served in the pit lane)
    seconds: float = 5.0  # for "time" penalties
    reason: str = ""

    def __post_init__(self):
        if not self.time >= 0:
            raise ValueError(f"penalty time must be >= 0 s, got {self.time!r}")
        if self.kind not in ("time", "drive-through"):
            raise ValueError(f"penalty kind must be 'time' or 'drive-through', got {self.kind!r}")
        if self.kind == "time" and not (0 < self.seconds < math.inf):
            raise ValueError(f"a time penalty needs seconds > 0, got {self.seconds!r}")


@dataclass(frozen=True)
class ControlEvent:
    time: float  # s of race time
    kind: str  # "flag", "extended", "retirement", "penalty", "penalty served", "penalty converted" or "ignored"
    flag: Flag  # race-control state after the event
    cars: tuple[int, ...]  # cars affected
    detail: str


class RaceControl:
    """Flag state machine plus the scripted incidents and penalties. The race applies them to the cars."""

    def __init__(self, incidents=(), penalties=(), rules: RaceControlRules = RaceControlRules()):
        self.rules = rules
        # incidents before penalties at the same time, otherwise script order
        self.script = sorted([*incidents, *penalties], key=lambda item: (item.time, isinstance(item, Penalty)))
        self.flag = Flag.GREEN
        self.zone: int | None = None  # segment index of the yellow zone
        self.ends_at = 0.0  # s: when YELLOW/VSC end; the earliest end of SAFETY_CAR
        self.events: list[ControlEvent] = []
        self._next = 0  # index of the first script item not yet handed out

    def due(self, time: float) -> list:
        """Script items whose time has come, in order; each is handed out once."""
        start = self._next
        while self._next < len(self.script) and self.script[self._next].time <= time:
            self._next += 1
        return self.script[start:self._next]

    def log(self, time: float, kind: str, cars: tuple[int, ...], detail: str) -> None:
        self.events.append(ControlEvent(time, kind, self.flag, cars, detail))

    def call(self, flag: Flag, time: float, duration: float, zone: int | None, cars: tuple[int, ...], reason: str):
        """Escalate to `flag`, or extend the current period if it is already at least as severe."""
        if flag > self.flag:
            old = self.flag
            check_transition(old, flag)
            self.flag, self.ends_at = flag, time + duration
            self.zone = zone if flag is Flag.YELLOW else None
            self.log(time, "flag", cars, f"{old.name} -> {flag.name}: {reason}")
        else:
            self.ends_at = max(self.ends_at, time + duration)
            self.log(time, "extended", cars, f"{self.flag.name} until {self.ends_at:.1f} s: {reason}")

    def clear(self, time: float, cars: tuple[int, ...], detail: str) -> None:
        check_transition(self.flag, Flag.GREEN)
        old, self.flag, self.zone = self.flag, Flag.GREEN, None
        self.log(time, "flag", cars, f"{old.name} -> GREEN: {detail}")

    def pace_factor(self, factor: float, in_zone: bool, leads: bool) -> float:
        """Time factor a car on track must run at, given its normal factor."""
        if self.flag is Flag.SAFETY_CAR:
            return self.rules.sc_factor if leads else self.rules.sc_catch_up_factor
        if self.flag is Flag.VSC:
            return self.rules.vsc_factor
        if self.flag is Flag.YELLOW and in_zone:
            return factor * (1 + self.rules.yellow_slowdown)
        return factor

    def overtaking_allowed(self, in_zone: bool) -> bool:
        return self.flag is Flag.GREEN or (self.flag is Flag.YELLOW and not in_zone)
