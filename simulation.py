import math

from physics import TYRE_GRIP, acceleration, corner_speed, deceleration

STEP = 1.0  # m, track resolution


def track_points(track):
    """Split the track into ~STEP-long pieces: (distance to next point, radius, gradient) per point."""
    points = []
    for segment in track.segments:
        n = max(1, round(segment.length / STEP))
        points += [(segment.length / n, segment.radius, segment.gradient)] * n
    return points


def simulate_lap(car, track, tyre_grip=TYRE_GRIP):
    """Flying lap. Returns (lap time in s, speed in m/s at each track point)."""
    spec = car.specification
    points = track_points(track)
    n = len(points)
    limit = [corner_speed(spec, radius, tyre_grip) for _, radius, _ in points]

    # Each pass runs two laps: the first only sets the speed at the line.
    speed = [0.0] * n
    v = 0.0
    for k in range(2 * n):  # full throttle out of every corner
        i = k % n
        ds, radius, gradient = points[i - 1]
        v = speed[i] = min(limit[i], math.sqrt(v * v + 2 * acceleration(spec, v, radius, gradient, tyre_grip) * ds))
    for k in reversed(range(2 * n)):  # brake late enough to make every corner
        i = k % n
        ds, radius, gradient = points[i]
        v = speed[i] = min(speed[i], math.sqrt(v * v + 2 * deceleration(spec, v, radius, gradient, tyre_grip) * ds))

    lap_time = sum(2 * points[i - 1][0] / (speed[i - 1] + speed[i]) for i in range(n))
    return lap_time, speed
