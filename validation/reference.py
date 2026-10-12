"""Load, check and convert the raw reference files (data/reference/raw) into plain numbers in SI units.

Every function raises ReferenceDataError, rather than guessing, when data is missing, malformed or too thin.
"""
import json
import re
import statistics
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "reference" / "raw"
TEAMS = ("Red Bull", "Ferrari", "McLaren", "Mercedes")  # constructors with a model car in cars.py
CLEAN_LAP_LIMIT = 1.07  # laps slower than 107 % of the driver's median count as disturbed (lap 1, stops, SC)
PIT_WINDOW = 5  # laps either side of a stop used for the reference pace
MIN_CLEAN_LAPS = 3  # fewer clean laps than this in the window: the stop is not measured
_LAP_TIME = re.compile(r"^(?:(\d+):)?(\d{1,2}(?:\.\d+)?)$")


class ReferenceDataError(ValueError):
    pass


def lap_time_seconds(text: str) -> float:
    """'1:19.327' -> 79.327 s; '59.9' -> 59.9 s. Rejects anything else."""
    match = _LAP_TIME.match(text.strip()) if isinstance(text, str) else None
    if not match:
        raise ReferenceDataError(f"not a lap time: {text!r}")
    minutes, seconds = match.groups()
    if minutes is not None and float(seconds) >= 60:
        raise ReferenceDataError(f"seconds out of range in {text!r}")
    return int(minutes or 0) * 60 + float(seconds)


def kph_to_mps(kph: float) -> float:
    return kph / 3.6


def load_race(path: Path) -> dict:
    """The single race object inside an Ergast-format response."""
    try:
        races = json.loads(Path(path).read_text())["MRData"]["RaceTable"]["Races"]
    except FileNotFoundError:
        raise ReferenceDataError(f"missing reference file {path}") from None
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ReferenceDataError(f"malformed reference file {path}: {error!r}") from None
    if len(races) != 1:
        raise ReferenceDataError(f"{path}: expected exactly one race, found {len(races)}")
    return races[0]


def _field(record: dict, *keys: str):
    value = record
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise ReferenceDataError(f"missing field {'/'.join(keys)} in {record!r:.120}")
        value = value[key]
    return value


def qualifying_best(season: int, raw: Path = RAW) -> dict[str, tuple[float, str]]:
    """Each modelled team's fastest qualifying lap (any session, either driver): {team: (s, driver code)}."""
    best: dict[str, tuple[float, str]] = {}
    for entry in _field(load_race(raw / f"{season}_qualifying.json"), "QualifyingResults"):
        team = _field(entry, "Constructor", "name")
        if team not in TEAMS:
            continue
        for session in ("Q1", "Q2", "Q3"):
            if entry.get(session):  # a driver knocked out early has no Q2/Q3 time
                time = lap_time_seconds(entry[session])
                if team not in best or time < best[team][0]:
                    best[team] = (time, _field(entry, "Driver", "code"))
    missing = set(TEAMS) - set(best)
    if missing:
        raise ReferenceDataError(f"{season}: no qualifying time for {sorted(missing)}")
    return best


def track_length(season: int, raw: Path = RAW) -> float:
    """m: median over drivers of fastest-lap average speed × fastest-lap time (same lap, so one lap length)."""
    lengths = []
    for result in _field(load_race(raw / f"{season}_results.json"), "Results"):
        fastest = result.get("FastestLap", {})
        if "AverageSpeed" in fastest and "Time" in fastest:
            if _field(fastest, "AverageSpeed", "units") != "kph":
                raise ReferenceDataError(f"unexpected speed units in {fastest!r}")
            speed = kph_to_mps(float(_field(fastest, "AverageSpeed", "speed")))
            lengths.append(speed * lap_time_seconds(_field(fastest, "Time", "time")))
    if len(lengths) < 3:
        raise ReferenceDataError(f"{season}: only {len(lengths)} laps with an average speed, need 3")
    return statistics.median(lengths)


def winner(season: int, raw: Path = RAW) -> dict:
    """The race winner: team, total race time (s), laps, and the laps on which it pitted."""
    race = load_race(raw / f"{season}_results.json")
    first = next((r for r in _field(race, "Results") if r.get("position") == "1"), None)
    if first is None:
        raise ReferenceDataError(f"{season}: no winner in the results")
    driver = _field(first, "Driver", "driverId")
    stops = [int(_field(s, "lap")) for s in _field(load_race(raw / f"{season}_pitstops.json"), "PitStops")
             if s.get("driverId") == driver]
    return {
        "team": _field(first, "Constructor", "name"),
        "driver": _field(first, "Driver", "code"),
        "time": int(_field(first, "Time", "millis")) / 1000,
        "laps": int(_field(first, "laps")),
        "stop_laps": stops,
    }


def lap_times(season: int, driver: str, raw: Path = RAW) -> dict[int, float]:
    """{lap number: s} for one driver's race."""
    laps = {}
    for lap in _field(load_race(raw / f"{season}_laps_{driver}.json"), "Laps"):
        timings = _field(lap, "Timings")
        if len(timings) != 1 or timings[0].get("driverId") != driver:
            raise ReferenceDataError(f"{season} {driver}: unexpected timings on lap {lap.get('number')}")
        laps[int(_field(lap, "number"))] = lap_time_seconds(_field(timings[0], "time"))
    if not laps:
        raise ReferenceDataError(f"{season} {driver}: no laps")
    return laps


def stop_loss(laps: dict[int, float], lap: int, stop_laps: list[int]) -> dict | None:
    """Time lost by the stop on `lap`: (in-lap + out-lap) − 2 × median clean lap within PIT_WINDOW laps.

    Clean laps exclude lap 1, every in- and out-lap, and laps above CLEAN_LAP_LIMIT × the race median.
    None if fewer than MIN_CLEAN_LAPS clean laps are available."""
    if lap not in laps or lap + 1 not in laps:
        raise ReferenceDataError(f"no in/out lap times around the stop on lap {lap}")
    median = statistics.median(laps.values())
    disturbed = {1} | {k for stop in stop_laps for k in (stop, stop + 1)}
    window = [laps[k] for k in range(lap - PIT_WINDOW, lap + PIT_WINDOW + 2)
              if k in laps and k not in disturbed and laps[k] <= CLEAN_LAP_LIMIT * median]
    if len(window) < MIN_CLEAN_LAPS:
        return None
    pace = statistics.median(window)
    return {"lap": lap, "loss": laps[lap] + laps[lap + 1] - 2 * pace, "pace": pace}


def pit_losses(season: int, raw: Path = RAW) -> list[dict]:
    """Measured stop_loss for every stop by a driver of the modelled teams; needs MIN_CLEAN_LAPS measured stops."""
    drivers = {_field(r, "Driver", "driverId") for r in _field(load_race(raw / f"{season}_results.json"), "Results")
               if _field(r, "Constructor", "name") in TEAMS}
    stops = [s for s in _field(load_race(raw / f"{season}_pitstops.json"), "PitStops") if s.get("driverId") in drivers]
    losses = []
    for driver in sorted(drivers):
        laps = lap_times(season, driver, raw)
        stop_laps = sorted(int(_field(s, "lap")) for s in stops if s["driverId"] == driver)
        for lap in stop_laps:
            measured = stop_loss(laps, lap, stop_laps)
            if measured is not None:
                losses.append({"driver": driver, **measured})
    if len(losses) < MIN_CLEAN_LAPS:
        raise ReferenceDataError(f"{season}: only {len(losses)} measurable stops")
    return losses
