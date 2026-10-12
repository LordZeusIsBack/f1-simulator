import math
from unittest import TestCase

import physics
import race
from abstract_classes import TyreCompound
from rl.env import ACTIONS, COMPOUND_ORDER, Observation, StepResult, StrategyEnv
from rl.evaluate import BASELINES, compare, run_episode, summarise
from rl.experiment import cross_entropy_search
from rl.policies import PIT, STAY, FixedOneStop, RandomPolicy, RuleBased, stay_out
from race_control import Flag

assert_raises = TestCase().assertRaises
QUIET = dict(neutralisation_chance=0.0, rain_chance=0.0)  # no random events: easy to reason about


def play(env, policy, seed=0):
    observation, info = env.reset(seed=seed)
    results = []
    while not results or not (results[-1].terminated or results[-1].truncated):
        results.append(env.step(policy(observation, info["action_mask"])))
        observation, info = results[-1].observation, results[-1].info
    return results


def test_construction_is_validated():
    for bad in (dict(laps=1), dict(laps=2.5), dict(team="Williams"), dict(pit_loss=-1), dict(dt=0),
                dict(rain_chance=1.5), dict(neutralisation_chance=-0.1), dict(opponents=4), dict(max_steps=0),
                dict(start_compound="soft")):
        with assert_raises(ValueError):
            StrategyEnv(**bad)


def test_reset_gives_a_bounded_observation_and_info():
    env = StrategyEnv(laps=5, **QUIET)
    with assert_raises(RuntimeError):
        env.step(STAY)  # no reset yet
    observation, info = env.reset(seed=1)
    assert isinstance(observation, Observation) and len(observation) == 19
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in observation)
    assert (observation.progress, observation.medium, observation.green, observation.stops) == (0.0, 1.0, 1.0, 0.0)
    assert info["lap"] == 0 and info["action_mask"] == (True,) * len(ACTIONS) and len(ACTIONS) == 6
    on_inters, _ = StrategyEnv(laps=5, start_compound=TyreCompound.INTERMEDIATE, **QUIET).reset(seed=1)
    assert on_inters.intermediate == 1.0 and on_inters.two_compounds == 1.0  # wet tyres exempt the car from the rule


def test_actions_are_validated_and_masked():
    env = StrategyEnv(laps=3, **QUIET)
    env.reset(seed=0)
    for bad in (-1, 6, 1.0, True, "1", None):
        with assert_raises(ValueError):
            env.step(bad)
    env.step(STAY)
    result = env.step(STAY)  # now on the last lap: pitting is impossible
    assert result.info["action_mask"] == (True, False, False, False, False, False)
    with assert_raises(ValueError):
        env.step(PIT[TyreCompound.HARD])


def test_step_result_and_state_transitions():
    env = StrategyEnv(laps=4, **QUIET)
    observation, _ = env.reset(seed=0)
    result = env.step(PIT[TyreCompound.HARD])  # pit at the end of lap 1
    assert isinstance(result, StepResult) and len(result) == 5
    assert isinstance(result.reward, float) and result.terminated is False and result.truncated is False
    assert result.observation.progress == 0.25 and result.observation.hard == 1.0 and result.observation.medium == 0.0
    assert result.observation.tyre_wear == 0.0 and result.observation.stops == 1 / 3 and result.observation.two_compounds == 1.0
    assert result.info["pit_stops"] == [(1, "hard")]
    second = env.step(STAY)
    assert second.observation.progress == 0.5 and second.observation.tyre_wear > 0
    assert second.observation.fuel < result.observation.fuel  # fuel burns


def test_rewards_sum_to_minus_the_race_time_and_point_the_right_way():
    env = StrategyEnv(laps=6, **QUIET)
    one_stop = play(env, FixedOneStop(at=0.5))
    total = sum(r.reward for r in one_stop)
    assert math.isclose(-total * env.reference_lap, one_stop[-1].info["total_time"], rel_tol=1e-12)
    two_stops = play(env, lambda obs, mask: PIT[TyreCompound.HARD] if obs.progress in (0.0, 0.5) else STAY)
    assert sum(r.reward for r in two_stops) < total  # a needless extra stop is punished
    never = play(env, stay_out)
    assert never[-1].info["penalty_time"] == 30.0  # two-compound rule
    penalty_free = play(StrategyEnv(laps=6, two_compound_rule=False, **QUIET), stay_out)
    assert math.isclose(sum(r.reward for r in penalty_free) - sum(r.reward for r in never), 30.0 / env.reference_lap,
                        rel_tol=1e-9)
    # the call at progress 0.5 (step 3) stops the car at the line just ahead: the stop's cost is in that same step
    assert one_stop[3].reward < one_stop[2].reward - 20.0 / env.reference_lap


def test_termination_and_truncation():
    env = StrategyEnv(laps=4, **QUIET)
    results = play(env, FixedOneStop())
    assert len(results) == 4 and results[-1].terminated and not results[-1].truncated
    assert all(not r.terminated for r in results[:-1]) and results[-1].observation.progress == 1.0
    with assert_raises(RuntimeError):
        env.step(STAY)  # episode over
    short = play(StrategyEnv(laps=4, max_steps=2, **QUIET), stay_out)
    assert len(short) == 2 and short[-1].truncated and not short[-1].terminated
    assert short[-1].info["finish_time"] is None


def test_seeded_episodes_are_reproducible():
    def rollout(env, seed):
        return [(r.observation, r.reward, r.info["scenario"]) for r in play(env, RuleBased(), seed)]

    env = StrategyEnv(laps=8)
    assert rollout(env, 7) == rollout(env, 7) == rollout(StrategyEnv(laps=8), 7)
    scenarios = {str(StrategyEnv(laps=8).reset(seed=s)[1]["scenario"]) for s in range(6)}
    assert len(scenarios) > 1  # seeds do change the scenario
    a, b = StrategyEnv(laps=8, seed=5), StrategyEnv(laps=8, seed=5)
    assert [a.reset()[1]["scenario"] for _ in range(3)] == [b.reset()[1]["scenario"] for _ in range(3)]


def test_baselines_run_and_behave_as_described():
    env = StrategyEnv(laps=8, **QUIET)
    for name, make in BASELINES.items():
        episode = run_episode(env, make(3), seed=3)
        assert episode["time"] > 0 and not episode["truncated"], name
    assert run_episode(env, FixedOneStop(), 0)["stops"] == 1 and run_episode(env, stay_out, 0)["stops"] == 0
    observation, info = env.reset(seed=0)
    mask = info["action_mask"]
    assert RuleBased()(observation._replace(wetness=0.5), mask) == PIT[TyreCompound.INTERMEDIATE]
    assert RuleBased()(observation._replace(wetness=0.9), mask) == PIT[TyreCompound.WET]
    assert RuleBased()(observation._replace(safety_car=1.0, green=0.0, progress=0.5), mask) == PIT[TyreCompound.HARD]
    assert RuleBased()(observation._replace(tyre_wear=0.8), mask) == PIT[TyreCompound.HARD]
    assert RuleBased()(observation._replace(progress=0.9), mask) == PIT[TyreCompound.HARD]  # final call
    assert RuleBased()(observation, mask) == STAY
    first, second = RandomPolicy(1), RandomPolicy(1)
    actions = [first(observation, mask) for _ in range(50)]
    assert actions == [second(observation, mask) for _ in range(50)]  # seeded
    assert actions.count(STAY) > 30 and set(actions) - {STAY}  # mostly stays out, sometimes pits


def test_integration_with_traffic_weather_and_race_control():
    env = StrategyEnv(laps=6, opponents=2, neutralisation_chance=1.0, rain_chance=1.0)
    results = play(env, RuleBased(), seed=11)
    scenario = results[-1].info["scenario"]
    assert scenario["rain"] and scenario["incidents"]
    assert any(r.observation.wetness > 0 for r in results)  # weather reaches the observation
    assert len(env._race.cars) == 3 and env._race.traffic is not None
    positions = {r.observation.position for r in results}
    assert positions <= {0.0, 0.5, 1.0}
    flags = [e for e in env._race.race_control.events if e.kind == "flag"]
    assert flags and flags[0].detail.split(":")[0].endswith((Flag.VSC.name, Flag.SAFETY_CAR.name))


def test_pit_call_sees_a_safety_car_that_starts_mid_lap():
    env = StrategyEnv(laps=10)
    results = play(env, RuleBased(), seed=16)  # this seed's scenario: a safety car from about 305 s
    assert results[0].info["scenario"]["incidents"][0][1] == "SAFETY_CAR"
    seen = [r for r in results if r.observation.safety_car == 1.0]
    assert seen and seen[0].info["flag"] == "SAFETY_CAR"
    assert results[-1].info["pit_stops"] == [(seen[0].info["lap"] + 1, "hard")]  # took the cheap stop at that line
    assert results[-1].info["penalty_time"] == 0.0


def test_environment_leaves_the_simulator_unchanged():
    play(StrategyEnv(laps=4), RuleBased(), seed=2)
    assert physics.TYRE_GRIP == 1.8 and race.PIT_LOSS == 22.0


def test_summary_statistics_on_known_numbers():
    results = {"base": [{"time": 100.0, "stops": 1, "penalty": 0.0}, {"time": 110.0, "stops": 1, "penalty": 0.0}],
               "other": [{"time": 90.0, "stops": 2, "penalty": 30.0}, {"time": 120.0, "stops": 0, "penalty": 0.0}]}
    base, other = summarise(results, "base")
    assert (base["mean"], base["diff_mean"], base["better"], base["worse"]) == (105.0, 0.0, 0, 0)
    assert (other["mean"], other["min"], other["max"], other["stops"], other["penalised"]) == (105.0, 90.0, 120.0, 1.0, 1)
    assert (other["diff_mean"], other["better"], other["worse"]) == (0.0, 1, 1)
    assert math.isclose(other["std"], math.sqrt(450.0)) and math.isclose(other["diff_std"], math.sqrt(200.0))


def test_policy_search_is_reproducible():
    env = StrategyEnv(laps=4, **QUIET)
    first = cross_entropy_search(env, (0,), iterations=1, population=3, elites=1, cem_seed=4)
    assert first == cross_entropy_search(env, (0,), iterations=1, population=3, elites=1, cem_seed=4)
    assert isinstance(first[0], RuleBased) and len(first[1]) == 1


def test_compare_uses_identical_scenarios_for_every_policy():
    results = compare({"a": lambda s: stay_out, "b": lambda s: FixedOneStop()}, [5, 6], laps=4)
    assert [e["seed"] for e in results["a"]] == [e["seed"] for e in results["b"]] == [5, 6]


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
