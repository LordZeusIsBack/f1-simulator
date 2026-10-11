from cars import CARS
from simulation import simulate_lap
from tracks import Monza


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


if __name__ == "__main__":
    main()
