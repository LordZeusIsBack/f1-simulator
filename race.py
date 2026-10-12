import math
from bisect import bisect_right
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import accumulate

from abstract_classes import Car, Track, TrackSegment, TyreCompound
from drivers import Driver
from physics import TYRE_GRIP
from simulation import simulate_lap, track_points
from strategy import PitStop, Strategy
from traffic import TrafficRules, can_attack, drs_enabled, required_advantage, time_factor
from tyres import COMPOUNDS, Compound, Tyres

GRID_SPACING = 8.0  # m between consecutive grid slots, model assumption
PIT_LOSS = 22.0  # s a stop costs compared with driving past the pits, placeholder
FUEL_PER_LAP = 1.9  # kg burned per lap, placeholder
FUEL_CAPACITY = 110.0  # kg, F1's 2019-2025 race-fuel limit used as the tank size
REFUEL_RATE = 10.0  # kg/s while refuelling, placeholder
FUEL_TOLERANCE = 1e-9  # kg, absorbs float rounding when checking fuel plans


@dataclass
class RaceCar:
    """One car in one race. `car` and `strategy` are shareable inputs; the other fields are this car's own state."""
    number: int
    team: str
    car: Car
    strategy: Strategy | None = None  # None: no stops, mediums, just enough fuel
    driver: Driver = Driver()
    distance: float = 0.0  # m since the start line, negative while still behind it on the grid
    finish_time: float | None = None  # s of race time at which the car completed the race distance
    laps: int = 0  # laps completed
    fuel: float = 0.0  # kg on board
    tyres: Tyres | None = None
    pit_exit: float = 0.0  # s of race time until which the car stands in the pits
    drs: bool = False  # DRS usable on this lap
    attack: "OvertakeEvent | None" = None  # pass in progress, with the numbers that allowed it
    held_by: int | None = None  # number of the car this one is stuck behind


@dataclass(frozen=True)
class OvertakeEvent:
    time: float  # s of race time at the end of the step it happened in
    lap: int  # the attacker's current lap
    attacker: int
    defender: int
    outcome: str  # "attempt" (in progress), "passed", "aborted" or "held up"
    advantage: float  # m/s attacker speed advantage when the attempt was decided
    required: float  # m/s advantage the rules required
    drs: bool  # attacker had DRS


@dataclass(frozen=True)
class PitEvent:
    number: int
    lap: int  # the stop was made as the car completed this lap
    time: float  # s of race time when the car stopped
    duration: float  # s stationary: pit loss + refuelling
    tyres_before: Tyres
    tyres_after: Tyres
    fuel_added: float  # kg


class LapProfile:
    """A flying lap turned into a distance <-> time lookup, for one tyre grip and fuel load."""

    def __init__(self, car: Car, track: Track, tyre_grip: float = TYRE_GRIP, fuel: float = 0.0):
        spec = car.specification
        _, speed = simulate_lap(Car(replace(spec, mass=spec.mass + fuel)), track, tyre_grip)
        self.speed = speed + speed[:1]  # m/s at each table entry
        self.distance, self.time = [0.0], [0.0]  # m and s at each track point; the last entry closes the lap
        for i, (ds, _, _) in enumerate(track_points(track)):
            self.distance.append(self.distance[-1] + ds)
            # same trapezoid as simulate_lap's lap time: average of the speeds at both ends of ds
            self.time.append(self.time[-1] + 2 * ds / (speed[i] + speed[(i + 1) % len(speed)]))

    def time_at(self, distance: float) -> float:
        """s from the start line to `distance` m (any lap, may be negative)."""
        laps, rest = divmod(distance, self.distance[-1])
        return laps * self.time[-1] + _interpolate(rest, self.distance, self.time)

    def distance_at(self, time: float) -> float:
        """Inverse of time_at: m covered from the start line after `time` s."""
        laps, rest = divmod(time, self.time[-1])
        return laps * self.distance[-1] + _interpolate(rest, self.time, self.distance)

    def speed_at(self, distance: float) -> float:
        """m/s at `distance` m from the start line (any lap)."""
        return _interpolate(distance % self.distance[-1], self.distance, self.speed)


# ponytail: keyed by object identity, so don't mutate a Car or Track while races use it.
# Saves recomputing identical laps (team-mates on the same plan); ~0.4 MB per Monza profile.
@lru_cache(maxsize=16)
def lap_profile(car: Car, track: Track, tyre_grip: float, fuel: float) -> LapProfile:
    return LapProfile(car, track, tyre_grip, fuel)


def _interpolate(x: float, xs: list[float], ys: list[float]) -> float:
    i = min(bisect_right(xs, x), len(xs) - 1)  # xs[i - 1] <= x < xs[i]
    return ys[i - 1] + (x - xs[i - 1]) / (xs[i] - xs[i - 1]) * (ys[i] - ys[i - 1])


class Race:
    """Race state: track, rules, cars in grid order, elapsed race time and the pit-stop log."""

    def __init__(
        self,
        track: Track,
        laps: int,
        grid: list[RaceCar],
        *,
        pit_loss: float = PIT_LOSS,
        fuel_per_lap: float = FUEL_PER_LAP,
        compounds: dict[TyreCompound, Compound] = COMPOUNDS,
        traffic: TrafficRules | None = TrafficRules(),
    ):
        if not isinstance(laps, int) or laps < 1:
            raise ValueError(f"laps must be a positive integer, got {laps!r}")
        if not grid:
            raise ValueError("a race needs at least one car")
        if len({car.number for car in grid}) != len(grid):
            raise ValueError("car numbers must be unique")
        if pit_loss < 0 or fuel_per_lap < 0:
            raise ValueError("pit_loss and fuel_per_lap cannot be negative")
        self.track = track
        self.laps = laps
        self.cars = grid
        self.pit_loss = pit_loss  # s
        self.fuel_per_lap = fuel_per_lap  # kg/lap
        self.compounds = compounds
        self.traffic = traffic  # None: cars ignore each other (V2 behaviour)
        self.time = 0.0  # s since the start
        self.race_distance = laps * track.length  # m
        self.pit_events: list[PitEvent] = []
        self.overtakes: list[OvertakeEvent] = []
        self._segment_starts = list(accumulate(segment.length for segment in track.segments))[:-1]
        self._strategies: dict[int, Strategy] = {}
        self._profiles: dict[int, LapProfile] = {}  # each car's profile for its current lap
        for slot, car in enumerate(grid):
            strategy = car.strategy or Strategy(TyreCompound.MEDIUM, laps * fuel_per_lap)
            self._check(car.number, strategy)
            self._strategies[car.number] = strategy
            car.distance = -slot * GRID_SPACING
            car.finish_time = None
            car.laps = 0
            car.fuel = strategy.fuel
            car.tyres = Tyres(strategy.compound)
            car.pit_exit = 0.0
            car.drs, car.attack, car.held_by = False, None, None
            self._profiles[car.number] = self._profile(car)

    def _check(self, number: int, strategy: Strategy) -> None:
        """Reject a plan that breaks the pit rules or runs out of fuel, before the race starts."""
        def invalid(reason):
            return ValueError(f"car #{number}: {reason}")

        if strategy.compound not in self.compounds:
            raise invalid(f"cannot start on {strategy.compound!r}")
        if not 0 <= strategy.fuel <= FUEL_CAPACITY:
            raise invalid(f"start fuel must be 0-{FUEL_CAPACITY} kg, got {strategy.fuel!r}")
        stop_laps = [stop.lap for stop in strategy.stops]
        if len(set(stop_laps)) != len(stop_laps):
            raise invalid("at most one stop per lap")
        for stop in strategy.stops:
            if not isinstance(stop.lap, int) or not 1 <= stop.lap < self.laps:
                raise invalid(f"stops must be after laps 1-{self.laps - 1}, got lap {stop.lap!r}")
            if stop.compound is not None and stop.compound not in self.compounds:
                raise invalid(f"cannot fit {stop.compound!r}")
            if stop.fuel < 0:
                raise invalid(f"cannot remove fuel (lap {stop.lap})")
            if stop.compound is None and stop.fuel == 0:
                raise invalid(f"the stop on lap {stop.lap} changes nothing")
        fuel = strategy.fuel
        for lap in range(1, self.laps + 1):
            if fuel < self.fuel_per_lap - FUEL_TOLERANCE:
                raise invalid(f"runs out of fuel on lap {lap}")
            fuel -= self.fuel_per_lap
            stop = strategy.stop_after(lap)
            if stop is not None:
                fuel += stop.fuel
                if fuel > FUEL_CAPACITY + FUEL_TOLERANCE:
                    raise invalid(f"refuelling after lap {lap} overfills the {FUEL_CAPACITY} kg tank")

    def _profile(self, car: RaceCar) -> LapProfile:
        return lap_profile(car.car, self.track, car.tyres.grip(self.compounds), car.fuel)

    @property
    def finished(self) -> bool:
        return all(car.finish_time is not None for car in self.cars)

    def laps_completed(self, car: RaceCar) -> int:
        return car.laps

    def step(self, dt: float) -> None:
        """Move every running car `dt` s further. With traffic, leader first, so each car sees where the car ahead now is."""
        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt!r}")
        end = self.time + dt
        factors: dict[int, float] = {}  # this step's time factor per car on track
        for car in (self.cars if self.traffic is None else self.standings()):
            if self.traffic is not None and self._on_track(car):
                self._drive(car, end, factors)
            else:
                self._advance(car, end, car.driver.time_factor())
        self.time = end

    def _drive(self, car: RaceCar, end: float, factors: dict[int, float]) -> None:
        """One step for a car on track: traffic effects, the pass decision, the move, then the events."""
        rules = self.traffic
        ahead = self.car_ahead(car)
        interval = self.interval(car, ahead) if ahead else math.inf
        segment = self._segment(car)
        factor = factors[car.number] = time_factor(rules, car.driver, segment, interval, car.drs)
        if car.attack and (ahead is None or car.attack.defender != ahead.number):
            car.attack = None  # the defender pitted or finished
        limit = None  # m the car may not pass this step
        if ahead and not car.attack and self._free_distance(car, end, factor) > ahead.distance - rules.min_gap:
            # both speeds at the attacker's spot: who is quicker through this part of the track
            advantage = self._speed(car, car.distance, factor) - self._speed(ahead, car.distance, factors[ahead.number])
            required = required_advantage(rules, car.driver, ahead.driver)
            attempt = OvertakeEvent(end, car.laps + 1, car.number, ahead.number, "attempt", advantage, required, car.drs)
            if can_attack(rules, segment, advantage, car.driver, ahead.driver):
                car.attack = attempt
            else:
                limit = max(car.distance, ahead.distance - rules.min_gap)
                if car.held_by != ahead.number:
                    self.overtakes.append(replace(attempt, outcome="held up"))
        car.held_by = ahead.number if limit is not None else None

        laps = car.laps
        self._advance(car, end, factor, limit)

        if car.attack and car.distance > ahead.distance:
            self.overtakes.append(replace(car.attack, time=end, outcome="passed"))
            car.attack = None
        elif car.attack and car.distance < ahead.distance - rules.min_gap:
            self.overtakes.append(replace(car.attack, time=end, outcome="aborted"))
            car.attack = None
        if car.laps > laps:  # DRS detection at the line
            ahead = self.car_ahead(car)
            car.drs = bool(ahead) and car.pit_exit <= end and drs_enabled(rules, car.laps + 1, self.interval(car, ahead))

    def _advance(self, car: RaceCar, end: float, factor: float = 1.0, limit: float | None = None) -> None:
        """Move one car up to race time `end` (or up to `limit` m), handling every line crossing and pit stop.

        `factor` stretches the car's profile time: 1.02 means 2 % slower than its flying lap."""
        clock = self.time
        while car.finish_time is None:
            clock = max(clock, car.pit_exit)  # a car in the pits waits there
            if clock >= end:
                return
            line = self._next_line(car)
            lap_start = line - self.track.length
            target = line if limit is None else min(line, limit)
            if target <= car.distance:
                return  # held up: no room to move
            profile = self._profiles[car.number]
            start = profile.time_at(car.distance - lap_start)  # s into the current lap
            to_target = (profile.time_at(target - lap_start) - start) * factor
            if clock + to_target > end:
                car.distance = lap_start + profile.distance_at(start + (end - clock) / factor)
                return
            clock += to_target  # exact arrival time
            car.distance = target
            if target < line:
                return  # reached the car ahead: wait behind it for the rest of the step
            if line > 0:
                self._complete_lap(car, clock)

    def _next_line(self, car: RaceCar) -> float:
        """m at which the car next crosses the line: 0 from the grid, else the end of its current lap."""
        return (car.laps + 1) * self.track.length if car.distance >= 0 else 0.0

    def _on_track(self, car: RaceCar) -> bool:
        return car.finish_time is None and car.pit_exit <= self.time

    def _segment(self, car: RaceCar) -> TrackSegment:
        return self.track.segments[bisect_right(self._segment_starts, car.distance % self.track.length)]

    def _free_distance(self, car: RaceCar, end: float, factor: float) -> float:
        """m the car would reach by `end` with nobody in its way (current lap profile, no line logic)."""
        lap_start = self._next_line(car) - self.track.length
        profile = self._profiles[car.number]
        return lap_start + profile.distance_at(profile.time_at(car.distance - lap_start) + (end - self.time) / factor)

    def _speed(self, car: RaceCar, distance: float, factor: float) -> float:
        """m/s the car would do at `distance`, from its current lap profile and this step's time factor."""
        return self._profiles[car.number].speed_at(distance) / factor

    def car_ahead(self, car: RaceCar) -> RaceCar | None:
        """Nearest car in front in race order that is on track (not finished, not in the pits); None for the leader."""
        ahead = [other for other in self.cars if self._on_track(other) and other.distance > car.distance]
        return min(ahead, key=lambda other: other.distance, default=None)

    def interval(self, car: RaceCar, ahead: RaceCar) -> float:
        """s `car` needs, at its current lap pace, to reach where `ahead` is now."""
        lap_start = self._next_line(car) - self.track.length
        profile = self._profiles[car.number]
        return profile.time_at(ahead.distance - lap_start) - profile.time_at(car.distance - lap_start)

    def _complete_lap(self, car: RaceCar, clock: float) -> None:
        """At the line: burn the lap's fuel, age the tyres, then finish or follow the strategy."""
        car.laps += 1
        car.fuel -= self.fuel_per_lap
        car.tyres = replace(car.tyres, laps=car.tyres.laps + 1)
        if car.laps == self.laps:
            car.finish_time = clock
            return
        stop = self._strategies[car.number].stop_after(car.laps)
        if stop is not None:
            self._pit(car, stop, clock)
        self._profiles[car.number] = self._profile(car)

    def _pit(self, car: RaceCar, stop: PitStop, clock: float) -> None:
        duration = self.pit_loss + stop.fuel / REFUEL_RATE  # refuelling adds to the stop, not in parallel
        tyres = Tyres(stop.compound) if stop.compound is not None else car.tyres
        self.pit_events.append(PitEvent(car.number, car.laps, clock, duration, car.tyres, tyres, stop.fuel))
        car.tyres = tyres
        car.fuel += stop.fuel
        car.pit_exit = clock + duration

    def run(self, dt: float = 0.5) -> list[RaceCar]:
        while not self.finished:
            self.step(dt)
        return self.standings()

    def standings(self) -> list[RaceCar]:
        """Finished cars by finish time, then running cars by distance. Ties keep grid order."""
        return sorted(
            self.cars,
            key=lambda car: (0, car.finish_time) if car.finish_time is not None else (1, -car.distance),
        )
