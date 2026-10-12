import json
import math
import tempfile
from pathlib import Path
from unittest import TestCase

import physics
import race
import tyres
from validation import calibrate, evaluate, metrics, reference
from validation.model import load_config, race_time

assert_raises = TestCase().assertRaises
REAL = reference.RAW  # the real, committed Jolpica-F1 files


def synthetic(files: dict) -> Path:
    """A temporary raw folder of SYNTHETIC test files: invented numbers, not F1 data."""
    folder = Path(tempfile.mkdtemp())
    for name, content in files.items():
        (folder / name).write_text(content if isinstance(content, str) else json.dumps(content))
    return folder


def race_file(**race_fields) -> dict:
    return {"MRData": {"RaceTable": {"Races": [race_fields]}}}


def laps_file(driver: str, times: list[str]) -> dict:
    return race_file(Laps=[{"number": str(n), "Timings": [{"driverId": driver, "time": t}]}
                           for n, t in enumerate(times, start=1)])


def test_lap_time_and_unit_conversion():
    assert [reference.lap_time_seconds(t) for t in ("1:19.327", "59.9", "60:00.0", " 1:01 ")] == [79.327, 59.9, 3600.0, 61.0]
    for bad in ("1:60.000", "abc", "", "1:2:3.4", "-1:19.3", None, 79.3):
        with assert_raises(reference.ReferenceDataError):
            reference.lap_time_seconds(bad)
    assert reference.kph_to_mps(360.0) == 100.0


def test_real_reference_files_load_and_check_out():
    best = reference.qualifying_best(2024)
    assert best["McLaren"] == (79.327, "NOR") and set(best) == set(reference.TEAMS)
    assert reference.qualifying_best(2025)["Red Bull"] == (78.792, "VER")
    assert math.isclose(reference.track_length(2024), 5793.0, abs_tol=1.0)  # matches the published 5.793 km
    won = reference.winner(2024)
    assert (won["driver"], won["team"], won["time"], won["laps"], won["stop_laps"]) == ("LEC", "Ferrari", 4480.727, 53, [15])
    assert len(reference.lap_times(2025, "max_verstappen")) == 53
    losses = reference.pit_losses(2024)
    assert len(losses) == 14 and all(15 < stop["loss"] < 40 for stop in losses)


def test_missing_malformed_and_insufficient_data_is_rejected():
    folder = synthetic({
        "2001_qualifying.json": "{not json",
        "2002_qualifying.json": {"MRData": {}},
        "2003_qualifying.json": {"MRData": {"RaceTable": {"Races": []}}},
        "2004_qualifying.json": race_file(QualifyingResults=[  # only one modelled team
            {"Constructor": {"name": "McLaren"}, "Driver": {"code": "AAA"}, "Q1": "1:20.000"}]),
        "2005_qualifying.json": race_file(QualifyingResults=[
            {"Constructor": {"name": team}, "Driver": {"code": "AAA"}, "Q1": "1:2x.000"} for team in reference.TEAMS]),
        "2006_results.json": race_file(Results=[{"FastestLap": {"Time": {"time": "1:20.0"}}}]),  # no average speeds
        "2008_qualifying.json": {"MRData": {"RaceTable": {"Races": [  # two (otherwise valid) races in one file
            {"QualifyingResults": [{"Constructor": {"name": t}, "Driver": {"code": "AAA"}, "Q1": "1:20.0"}
                                   for t in reference.TEAMS]}] * 2}}},
        "2009_results.json": race_file(Results=[  # only two laps with an average speed
            {"FastestLap": {"Time": {"time": "1:20.0"}, "AverageSpeed": {"units": "kph", "speed": "260.0"}}}] * 2),
    })
    for season in (2000, 2001, 2002, 2003, 2004, 2005, 2008):  # missing, malformed, shape, no race, team, time, 2 races
        with assert_raises(reference.ReferenceDataError):
            reference.qualifying_best(season, folder)
    for season in (2006, 2009):
        with assert_raises(reference.ReferenceDataError):
            reference.track_length(season, folder)
    with assert_raises(reference.ReferenceDataError):
        reference.track_length(2025)  # real file, but 2025 publishes no average speeds


def test_pit_loss_measurement_on_a_known_example():
    laps = {1: 90.0, **{n: 80.0 for n in range(2, 10)}, 10: 85.0, 11: 95.0, **{n: 80.0 for n in range(12, 20)}}
    assert reference.stop_loss(laps, 10, [10]) == {"lap": 10, "loss": 85.0 + 95.0 - 2 * 80.0, "pace": 80.0}
    laps[12] = laps[13] = laps[14] = 200.0  # slow (e.g. safety car) laps are not "clean"
    for n in range(5, 10):
        laps[n] = 200.0
    assert reference.stop_loss(laps, 10, [10]) is None  # too few clean laps left to measure
    with assert_raises(reference.ReferenceDataError):
        reference.stop_loss(laps, 19, [19])  # no out-lap
    folder = synthetic({  # a whole race file with a single stop: too few stops to report
        "2007_results.json": race_file(Results=[{"Driver": {"driverId": "aaa"}, "Constructor": {"name": "McLaren"}}]),
        "2007_pitstops.json": race_file(PitStops=[{"driverId": "aaa", "lap": "10"}]),
        "2007_laps_aaa.json": laps_file("aaa", ["1:30.0"] + ["1:20.0"] * 8 + ["1:25.0", "1:35.0"] + ["1:20.0"] * 8),
    })
    with assert_raises(reference.ReferenceDataError):
        reference.pit_losses(2007, folder)


def test_metrics_on_known_examples():
    model, ref = [10.0, 12.0, 9.0], [10.0, 10.0, 10.0]
    assert metrics.error(12.0, 10.0) == 2.0 and metrics.relative_error(12.0, 10.0) == 0.2
    assert math.isclose(metrics.mean_error(model, ref), 1 / 3)
    assert metrics.mean_absolute_error(model, ref) == 1.0
    assert math.isclose(metrics.mean_absolute_percentage_error(model, ref), 10.0)
    assert metrics.max_absolute_error(model, ref) == 2.0
    for bad in (([], []), ([1.0], [1.0, 2.0])):
        with assert_raises(ValueError):
            metrics.mean_absolute_error(*bad)
    with assert_raises(ValueError):
        metrics.relative_error(1.0, 0.0)


def test_calibration_is_reproducible_and_matches_the_committed_config():
    first, second = calibrate.calibrate(), calibrate.calibrate()
    assert first == second
    committed = json.loads((Path(calibrate.CONFIG) / "calibrated.json").read_text())
    assert committed == json.loads(json.dumps(first))


def test_calibration_refuses_an_impossible_fit():
    with assert_raises(ValueError):
        calibrate.fit_tyre_grip({"McLaren": 10.0}, low=1.0, high=2.0)  # no grip in range gives a 10 s lap
    with assert_raises(ValueError):
        calibrate.fit_pit_loss([20.0, 21.0])


def test_baseline_and_calibrated_configs_are_separate_and_leave_the_simulator_alone():
    baseline, calibrated = load_config("baseline"), load_config("calibrated")
    assert (baseline["tyre_grip"], baseline["pit_loss"]) == (physics.TYRE_GRIP, race.PIT_LOSS)  # baseline = code
    assert calibrated["baseline"] == {"tyre_grip": baseline["tyre_grip"], "pit_loss": baseline["pit_loss"]}
    assert (calibrated["tyre_grip"], calibrated["pit_loss"]) != (baseline["tyre_grip"], baseline["pit_loss"])
    before = dict(tyres.COMPOUNDS)
    race_time(calibrated, "McLaren", 2, [1])
    assert physics.TYRE_GRIP == 1.8 and race.PIT_LOSS == 22.0 and tyres.COMPOUNDS == before
    for bad in ({"tyre_grip": 1.8}, {"tyre_grip": -1, "pit_loss": 22.0}, {"tyre_grip": "1.8", "pit_loss": 22.0}):
        with assert_raises(ValueError):
            load_config("bad", synthetic({"bad.json": bad}))


def test_committed_report_is_up_to_date():
    assert evaluate.render(evaluate.evaluate()) == evaluate.REPORT.read_text()


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
