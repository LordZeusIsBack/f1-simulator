import math
from unittest import TestCase

from abstract_classes import TyreCompound
from control import WEAR_EXPONENT, CarControl, wear_factor
from drivers import Driver
from driving import DriverAction as A
from race import Race, RaceCar
from rl.driver_env import ACTIONS, DECISION_DISTANCE, DriverEnv, Observation
from driving import BALANCED
from rl.driver_learning import (CONSERVE, MAINTAIN, SMOKE, QLearner, RuleBased, baselines, experiment, push, report,
                                run_episode, state, train)
from test_race import FAST
from test_simulation import Stadium
from tyres import Tyres

assert_raises = TestCase().assertRaises
ENV = DriverEnv(laps=2, opponents=2, seed=0)  # one instance: profiles and envelopes are cached across tests
ALONE = DriverEnv(laps=1, opponents=0)


def play(env, choose, seed):
    observation, info = env.reset(seed=seed)
    steps, done = [], False
    while not done:
        action = choose(observation, info)
        result = env.step(action)
        steps.append((action, result))
        observation, info, done = result.observation, result.info, result.terminated or result.truncated
    return steps


def test_wear_follows_the_grip_share_and_the_tyre_management_skill():
    assert wear_factor(1.0, 0.0) == wear_factor(1.0, 1.0) == 1.0  # at the limit every driver wears the same
    assert math.isclose(wear_factor(0.9, 0.5), 0.9 ** WEAR_EXPONENT)
    assert wear_factor(0.9, 1.0) < wear_factor(0.9, 0.5) < wear_factor(0.9, 0.0) < wear_factor(0.97, 0.0) < 1.0
    assert Tyres(TyreCompound.MEDIUM, 3).wear() == Tyres(TyreCompound.MEDIUM, 3, used=None).wear()  # default unchanged
    assert Tyres(TyreCompound.MEDIUM, 3, used=1.5).wear() == Tyres(TyreCompound.MEDIUM, 1).wear() * 1.5

    def worn(action, skill):
        car = RaceCar(1, "X", FAST, driver=Driver(tyre_management=skill), control=CarControl(action))
        Race(Stadium(), 3, [car], traffic=None).run(0.5)
        return car.tyres

    pushing = worn(A.ATTACK, 0.5)
    assert pushing.laps == 3 and math.isclose(pushing.used, 3.0)  # same wear as a car following its profile
    assert worn(A.CONSERVE_TYRES, 1.0).used < worn(A.CONSERVE_TYRES, 0.5).used < worn(A.MAINTAIN_PACE, 0.5).used < 3.0
    uncontrolled = RaceCar(1, "X", FAST)
    Race(Stadium(), 3, [uncontrolled], traffic=None).run(0.5)
    assert uncontrolled.tyres == Tyres(TyreCompound.MEDIUM, 3)  # cars without control: unchanged


def test_environment_settings_are_validated():
    for bad in ({"laps": 0}, {"laps": 1.5}, {"track": "Nowhere"}, {"team": "Nobody"}, {"opponents": 4},
                {"wear_price": -1.0}, {"wear_price": math.inf}, {"dt": 0.0}, {"dt": 2.0}, {"max_steps": 0},
                {"driver": "fast"}):
        with assert_raises(ValueError):
            DriverEnv(**bad)


def test_reset_and_step_contracts():
    with assert_raises(RuntimeError):
        DriverEnv(laps=1, opponents=0).step(MAINTAIN)  # no reset yet
    observation, info = ENV.reset(seed=3)
    assert isinstance(observation, Observation) and len(info["action_mask"]) == len(ACTIONS) == 4
    assert info["action_mask"][MAINTAIN] and info["action_mask"][CONSERVE] and info["driver_observation"] is not None
    for bad in (-1, 4, 1.0, True, "0"):
        with assert_raises(ValueError):
            ENV.step(bad)
    start = info["distance"]
    result = ENV.step(MAINTAIN)
    assert set(result._fields) == {"observation", "reward", "terminated", "truncated", "info"}
    assert result.info["distance"] >= start + DECISION_DISTANCE and not result.terminated and not result.truncated
    assert math.isclose(result.reward, -(result.info["time_lost"] + result.info["wear_cost"]))


def test_unavailable_actions_are_rejected():
    observation, info = ALONE.reset(seed=0)
    assert info["action_mask"] == (True, False, False, True)  # alone: no car to attack or defend against
    for action in (1, 2):
        with assert_raises(ValueError):
            ALONE.step(action)


def test_observations_stay_in_bounds_and_hide_the_scenario():
    for seed in (0, 1):
        for action, result in play(ENV, lambda o, i: push(o, i), seed):
            o = result.observation
            assert all(0.0 <= value <= 1.0 for name, value in o._asdict().items() if name != "closing")
            assert -1.0 <= o.closing <= 1.0
    assert not {"pace", "racecraft", "skill", "wear_price", "seed"} & set(Observation._fields)


def test_episode_ends_at_the_finish_and_rewards_add_up():
    steps = play(ALONE, lambda o, i: MAINTAIN, seed=0)
    *middle, (_, last) = steps
    assert last.terminated and not any(r.terminated or r.truncated for _, r in middle)
    assert last.info["finish_time"] is not None and last.observation.progress == 1.0
    assert len(steps) == math.ceil(ALONE.track.length / DECISION_DISTANCE)  # alone: starts on the line
    total = sum(r.reward for _, r in steps)
    reference = ALONE.reference.time_at(ALONE.track.length) - ALONE.reference.time_at(0.0)
    wear = last.info["tyre_wear"] * ALONE.wear_price
    assert math.isclose(-total, last.info["finish_time"] - reference + wear, abs_tol=1e-9)
    with assert_raises(RuntimeError):
        ALONE.step(MAINTAIN)  # the episode is over
    env = DriverEnv(laps=1, opponents=0, max_steps=3)
    steps = play(env, lambda o, i: MAINTAIN, seed=0)
    assert len(steps) == 3 and steps[-1][1].truncated and not steps[-1][1].terminated


def test_actions_change_the_motion_time_and_wear():
    def episode(action):
        steps = play(ALONE, lambda o, i: action, seed=0)
        info = steps[-1][1].info
        return info["finish_time"], info["tyre_wear"], sum(r.info["time_lost"] for _, r in steps)

    maintain, conserve = episode(MAINTAIN), episode(CONSERVE)
    assert conserve[0] > maintain[0] + 1.0  # slower by physics, not a lap-time bonus
    assert conserve[1] < maintain[1]  # and wears the tyres less
    assert conserve[2] > maintain[2] > 0.0
    ALONE.reset(seed=0)
    car = ALONE._car
    ALONE.step(CONSERVE)
    assert car.control.action is A.CONSERVE_TYRES  # the agent's action reached the controller


def test_wear_price_trades_time_against_tyres():
    free = DriverEnv(laps=1, opponents=0, wear_price=0.0)
    costly = DriverEnv(laps=1, opponents=0, wear_price=400.0)

    def cost(env, action):
        return -sum(r.reward for _, r in play(env, lambda o, i: action, seed=0))

    assert cost(free, MAINTAIN) < cost(free, CONSERVE)  # tyres free: the faster style costs less
    assert cost(costly, CONSERVE) < cost(costly, MAINTAIN)  # tyres dear: saving them pays


def test_reset_is_deterministic_and_seeds_differ():
    first = [(a, r.reward, r.observation) for a, r in play(ENV, push, seed=5)]
    assert first == [(a, r.reward, r.observation) for a, r in play(ENV, push, seed=5)]
    assert first != [(a, r.reward, r.observation) for a, r in play(ENV, push, seed=6)]
    ENV.reset(seed=5)
    scenario = ENV.scenario
    ENV.reset(seed=5)
    assert ENV.scenario == scenario and len(scenario["rivals"]) == 2


def test_baselines_choose_what_their_names_say():
    observation, info = ENV.reset(seed=1)
    policies = baselines(ENV.driver)
    assert set(policies) == {"maintain", "push", "conserve", "rule conservative", "rule balanced", "rule aggressive"}
    for name, policy in policies.items():
        assert info["action_mask"][policy(observation, info)], name
    assert policies["maintain"](observation, info) == MAINTAIN and policies["conserve"](observation, info) == CONSERVE
    alone = {"action_mask": (True, False, False, True)}
    assert push(None, alone) == MAINTAIN and push(None, {"action_mask": (True, False, True, True)}) == 2
    adapter = RuleBased(BALANCED, ENV.driver)
    expected = ACTIONS.index(BALANCED(info["driver_observation"], ENV.driver).action)
    assert adapter(observation, info) == expected
    assert RuleBased(BALANCED, ENV.driver)(observation, {**info, "driver_observation": None}) == MAINTAIN


def test_q_learning_updates_and_plays_greedily():
    learner = QLearner(alpha=0.5, gamma=0.9, seed=0)
    observation, info = ALONE.reset(seed=0)
    mask = info["action_mask"]
    assert learner.act(observation, mask) == MAINTAIN  # nothing learned: falls back to MAINTAIN_PACE
    learner.update(observation, CONSERVE, -1.0, observation, mask, terminal=True)
    learner.update(observation, MAINTAIN, -2.0, observation, mask, terminal=True)
    s = state(observation)
    assert learner.q[s][CONSERVE] == -0.5 and learner.q[s][MAINTAIN] == -1.0
    assert learner.act(observation, mask) == CONSERVE  # the better tried action
    learner.update(observation, CONSERVE, -1.0, observation, mask, terminal=False)  # bootstraps on the best next value
    assert math.isclose(learner.q[s][CONSERVE], -0.5 + 0.5 * (-1.0 + 0.9 * -0.5 - -0.5))
    assert learner.act(observation, (True, False, False, False)) == MAINTAIN  # never an unavailable action
    assert all(0 <= v < 3 for v in state(observation)[:2]) and len(state(observation)) == 6


def test_training_and_evaluation_are_seeded_and_report():
    settings = {**SMOKE, "episodes": 2, "runs": 1}
    env_kwargs = {**settings["env"], "opponents": 1}
    a, returns_a = train(env_kwargs, 100.0, 0, settings)
    b, returns_b = train(env_kwargs, 100.0, 0, settings)
    assert returns_a == returns_b and a.q == b.q and len(returns_a) == 2
    episode = run_episode(DriverEnv(**env_kwargs), a, seed=10_000)
    assert episode["finish_time"] > 0 and sum(episode["actions"].values()) > 0
    record = experiment({**settings, "env": env_kwargs, "wear_prices": [100.0], "processes": 1,
                         "eval_seeds": [10_000, 10_001]})
    rows = record["conditions"]["100.0"]["summary"]["policies"]
    assert set(rows) == {*baselines(Driver()), "Q-learning run 0"}
    assert "Wear price 100" in report(record)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
