import sys

from cars import CARS
from race import Race, RaceCar
from simulation import simulate_lap
from tracks import Monza

CARS_PER_TEAM = 2
RACE_LAPS = 53  # Monza's Grand Prix distance
DT = 0.5  # s per race step


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
        print(f"{position:>2}. #{car.number:<2} {car.team:<10} lap {race.laps_completed(car):>2}  {gap}")


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
    entries = [(team, car) for team, car in CARS.items() for _ in range(CARS_PER_TEAM)]
    grid = [RaceCar(number, team, car) for number, (team, car) in enumerate(entries, start=1)]
    race = Race(track, laps, grid)

    while race.laps_completed(race.standings()[0]) < 1:
        race.step(DT)
    print_standings(race, "After lap 1")
    race.run(DT)
    print_standings(race, f"Final classification ({laps}-lap race)")


if __name__ == "__main__":
    main()
