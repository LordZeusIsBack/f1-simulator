import sys

from abstract_classes import TyreCompound
from cars import CARS
from race import FUEL_PER_LAP, Race, RaceCar
from simulation import simulate_lap
from strategy import PitStop, Strategy
from tracks import Monza

RACE_LAPS = 53  # Monza's Grand Prix distance
DT = 0.1  # s per race step; traffic decisions are made once per step


def strategies(laps):
    """Each team runs one car on each plan, so the two plans meet on identical cars."""
    fuel = laps * FUEL_PER_LAP
    return [
        Strategy(TyreCompound.MEDIUM, fuel, name="no stop (M)"),
        Strategy(TyreCompound.MEDIUM, fuel, (PitStop(laps // 2, TyreCompound.HARD),), name="1 stop (M-H)"),
    ]


def print_standings(race, title):
    print(f"\n{title} (race time {race.time:.1f} s)")
    standings = race.standings()
    leader = standings[0]
    for position, car in enumerate(standings, start=1):
        if car.finish_time is None:
            gap = f"{car.distance - leader.distance:+9.1f} m"
        elif car is leader:
            gap = f"{car.finish_time:9.3f} s"
        else:
            gap = f"{car.finish_time - leader.finish_time:+9.3f} s"
        print(
            f"{position:>2}. #{car.number:<2} {car.team:<10} {car.strategy.name:<13}"
            f" lap {race.laps_completed(car):>2}  {gap}"
        )


def print_pit_stops(race):
    print("\nPit stops")
    for stop in race.pit_events:
        before, after = stop.tyres_before, stop.tyres_after
        print(
            f"#{stop.number:<2} after lap {stop.lap:>2} at {stop.time:7.1f} s:"
            f" {before.compound.value} ({before.laps} laps, {before.wear(race.compounds):.0%} worn)"
            f" -> {after.compound.value}, +{stop.fuel_added:.1f} kg fuel, {stop.duration:.1f} s"
        )


def print_overtakes(race):
    passes = [event for event in race.overtakes if event.outcome == "passed"]
    held = sum(event.outcome == "held up" for event in race.overtakes)
    print(f"\nOvertakes ({len(passes)} passes; cars were held up behind another {held} times)")
    for event in passes:
        print(
            f"lap {event.lap:>2} at {event.time:7.1f} s: #{event.attacker} passed #{event.defender}"
            f" ({event.advantage:+.1f} m/s, needed {event.required:.1f}{', DRS' if event.drs else ''})"
        )


def main():
    track = Monza()
    print(f"{track.name} ({track.length:.0f} m)")

    for name, car in CARS.items():
        lap_time, speed = simulate_lap(car, track)
        minutes, seconds = divmod(lap_time, 60)
        print(
            f"{name:<10} {minutes:.0f}:{seconds:06.3f}"
            f"  top {max(speed) * 3.6:3.0f} km/h  slowest {min(speed) * 3.6:3.0f} km/h"
        )

    laps = int(sys.argv[1]) if len(sys.argv) > 1 else RACE_LAPS
    plans = strategies(laps)
    entries = [(team, car, plan) for team, car in CARS.items() for plan in plans]
    grid = [RaceCar(number, team, car, plan) for number, (team, car, plan) in enumerate(entries, start=1)]
    race = Race(track, laps, grid)

    while race.laps_completed(race.standings()[0]) < 1:
        race.step(DT)
    print_standings(race, "After lap 1")
    race.run(DT)
    print_standings(race, f"Final classification, {laps}-lap race")
    print_pit_stops(race)
    print_overtakes(race)


if __name__ == "__main__":
    main()
