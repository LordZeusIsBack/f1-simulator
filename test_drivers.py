"""P2-V1: the driver profile. Skill storage and validation for every skill; behaviour only for attack and defence,
the only new skills with an effect in this version."""
import math
from dataclasses import FrozenInstanceError, fields
from unittest import TestCase

from abstract_classes import TyreCompound
from drivers import Driver
from race import Race, RaceCar
from strategy import Strategy
from test_race import FAST
from test_simulation import Stadium
from test_traffic import passes, run
from traffic import TrafficRules, required_advantage
from weather import Weather, WeatherPoint

assert_raises = TestCase().assertRaises
SKILLS = [field.name for field in fields(Driver)][1:]
DEFAULTS = {"pace": 1.0, "racecraft": 0.5, "attack": 0.5, "defence": 0.5,
            "tyre_management": 0.5, "consistency": 0.5, "wet_weather": 0.5}
PROFILE_ONLY = ("tyre_management", "consistency", "wet_weather")


def test_existing_constructors_and_time_factor_still_work():
    assert Driver().name == "" and Driver(name="Ada").name == "Ada"
    old = Driver("A", 0.5, 1)  # V3 positional order: name, pace, racecraft
    assert (old.pace, old.racecraft) == (0.5, 1)
    assert Driver().time_factor() == 1.0
    assert math.isclose(Driver(pace=0.0).time_factor(), 1.01) and math.isclose(Driver(pace=0.5).time_factor(), 1.005)


def test_every_skill_has_its_documented_default():
    assert SKILLS == list(DEFAULTS)
    assert {skill: getattr(Driver(), skill) for skill in SKILLS} == DEFAULTS


def test_lower_middle_and_upper_values_are_stored():
    for skill in SKILLS:
        for value in (0, 0.0, 0.5, 1, 1.0):
            assert getattr(Driver(**{skill: value}), skill) == value


def test_invalid_values_are_rejected_with_the_skill_named():
    for skill in SKILLS:
        bad_values = [True, False, "0.5", math.nan, math.inf, -math.inf, -0.01, 1.01, [0.5]]
        if skill not in ("attack", "defence"):
            bad_values.append(None)  # None means "use racecraft" only for attack and defence
        for bad in bad_values:
            with assert_raises(ValueError) as caught:
                Driver(**{skill: bad})
            assert str(caught.exception).startswith(f"{skill} must be")


def test_attack_and_defence_default_to_racecraft_unless_given():
    general = Driver(racecraft=0.8)
    assert general.attack == general.defence == 0.8
    split = Driver(racecraft=0.8, attack=0.1)
    assert (split.racecraft, split.attack, split.defence) == (0.8, 0.1, 0.8)
    assert Driver(racecraft=0.7) == Driver(racecraft=0.7, attack=0.7, defence=0.7)  # same resolved profile
    with assert_raises(ValueError) as caught:
        Driver(racecraft=2.0)
    assert str(caught.exception).startswith("racecraft must be")  # reported before attack inherits it


def test_two_drivers_keep_independent_frozen_profiles():
    a = Driver("Alpha", pace=0.9, attack=0.2, defence=0.9, tyre_management=0.1, consistency=0.3, wet_weather=1.0)
    b = Driver("Bravo", pace=0.4, attack=0.8, defence=0.1, tyre_management=0.7, consistency=0.6, wet_weather=0.0)
    assert [getattr(a, s) for s in SKILLS] == [0.9, 0.5, 0.2, 0.9, 0.1, 0.3, 1.0]
    assert [getattr(b, s) for s in SKILLS] == [0.4, 0.5, 0.8, 0.1, 0.7, 0.6, 0.0]
    with assert_raises(FrozenInstanceError):
        a.attack = 1.0


def test_required_advantage_uses_attacker_attack_and_defender_defence_only():
    rules = TrafficRules()  # 2.0 m/s margin, 1.0 m/s per unit
    attacker, defender = Driver(attack=1.0, defence=0.0), Driver(attack=0.0, defence=0.0)
    assert required_advantage(rules, attacker, defender) == 1.0
    assert required_advantage(rules, attacker, Driver(attack=1.0, defence=0.0)) == 1.0  # defender's attack: no effect
    assert required_advantage(rules, Driver(attack=1.0, defence=1.0), defender) == 1.0  # attacker's defence: no effect
    assert required_advantage(rules, Driver(attack=0.0), Driver(defence=1.0)) == 3.0
    assert required_advantage(rules, Driver(), Driver()) == 2.0  # defaults: same as V3's equal racecraft


def test_defence_alone_decides_whether_a_pass_happens():
    rules = TrafficRules(drs_from_lap=99, overtake_margin=0.6, racecraft_effect=0.5)  # as test_traffic's close fight

    def fight(defence, defender_attack=0.5):
        grid = [RaceCar(1, "A", FAST, driver=Driver(pace=0.0, attack=defender_attack, defence=defence)),
                RaceCar(2, "B", FAST, driver=Driver(pace=1.0, attack=1.0))]
        return passes(run(grid, laps=6, rules=rules)[0])

    assert fight(defence=0.0) == [(2, 1)]
    assert fight(defence=1.0) == []
    assert fight(defence=1.0, defender_attack=0.0) == fight(defence=1.0, defender_attack=1.0) == []


def test_profile_only_skills_do_not_change_a_race_yet():
    """Guards the P2-V1 documentation's claim: these skills are stored, not used. Wet race, tyre wear, traffic.
    Since P2-V4, tyre_management sets the wear of cars with a CarControl (test_driver_env); these cars have none."""
    def race(value):
        skills = dict.fromkeys(PROFILE_ONLY, value)
        grid = [RaceCar(1, "A", FAST, Strategy(TyreCompound.SOFT, 20.0), Driver(pace=0.5, **skills)),
                RaceCar(2, "B", FAST, Strategy(TyreCompound.MEDIUM, 20.0), Driver(**skills))]
        weather = Weather([WeatherPoint(0, 20.0), WeatherPoint(20, 20.0, 8.0)])
        r = Race(Stadium(), 6, grid, weather=weather)
        r.run(0.1)
        return [car.finish_time for car in grid], r.overtakes

    first = race(0.0)
    assert first == race(1.0) == race(0.0) and first[1]  # identical (and deterministic), with passing to compare


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
