import copy
import json
import math
import random
import statistics
import tempfile
from pathlib import Path
from unittest import TestCase

import research.scenario_coverage as experiment
from research.cem import cross_entropy
from research.config import ConfigError, load_config, validate
from research.runner import EpisodeSpec, code_digest, env_key, run_spec, run_specs, stratum
from research.stats import bootstrap_ci, paired, summary
from rl.env import StrategyEnv
from rl.policies import FixedOneStop, RuleBased, stay_out

assert_raises = TestCase().assertRaises
CONFIGS = Path(experiment.HERE) / "configs"
BOUNDS = {"wear_limit": [0.3, 1.0], "neutral_from": [0.0, 0.8], "neutral_to": [0.2, 1.0], "final_call": [0.6, 0.98]}


def tiny_config(**changes) -> dict:
    """A 3-lap, minimal-budget configuration: exercises the whole pipeline in seconds (not a research result)."""
    config = {
        "name": "tiny", "question": "pipeline test", "decision_rule": "pipeline test", "laps": 3,
        "env": {"team": "McLaren", "track": "Monza"},
        "designs": {"random": [{"neutralisation_chance": 0.5, "rain_chance": 0.25, "seeds": [0]}],
                    "stratified": [{"neutralisation_chance": 1.0, "rain_chance": 0.0, "seeds": [0]}]},
        "cem": {"runs": [0, 1], "iterations": 1, "population": 2, "elites": 1, "bounds": copy.deepcopy(BOUNDS)},
        "evaluation": {"neutralisation_chance": 0.5, "rain_chance": 0.25, "seeds_from": 1000, "episodes": 3,
                       "baselines": ["rule-based", "fixed one-stop"]},
        "sensitivity": {}, "statistics": {"bootstrap_resamples": 200, "bootstrap_seed": 0, "confidence": 0.95},
        "processes": 1, "max_failed_episodes": 0,
    }
    config.update(changes)
    return config


def write(config: dict) -> Path:
    path = Path(tempfile.mkdtemp()) / "config.json"
    path.write_text(json.dumps(config))
    return path


class Exploding:
    """A policy that fails on its third call: used to test failure handling."""

    def __init__(self):
        self.calls = 0

    def __call__(self, observation, mask):
        self.calls += 1
        if self.calls == 3:
            raise RuntimeError("deliberate failure")
        return 0


def test_committed_configs_load():
    for name in ("scenario_coverage", "smoke"):
        config = load_config(CONFIGS / f"{name}.json")
        assert config["name"] == name


def test_invalid_configurations_are_rejected():
    def broken(mutate):
        config = tiny_config()
        mutate(config)
        return config

    cases = [
        lambda c: c.pop("laps"),
        lambda c: c.update(extra=1),
        lambda c: c.update(laps=1),
        lambda c: c.update(question=""),
        lambda c: c["designs"].pop("stratified"),
        lambda c: c["designs"]["stratified"][0]["seeds"].append(1),  # unequal training budgets
        lambda c: c["designs"]["random"][0].update(rain_chance=1.5),
        lambda c: c["cem"].update(elites=3),
        lambda c: c["cem"].update(runs=[]),
        lambda c: c["cem"]["bounds"].update(wear_limit=[0.8, 1.0]),  # excludes the hand-set 0.75
        lambda c: c["cem"]["bounds"].update(final_call=[0.9, 0.9]),
        lambda c: c["evaluation"].update(seeds_from=0),  # overlaps training
        lambda c: c["evaluation"].update(baselines=["fixed one-stop"]),
        lambda c: c["evaluation"].update(baselines=["rule-based", "oracle"]),
        lambda c: c["statistics"].update(confidence=1.0),
        lambda c: c["statistics"].update(bootstrap_resamples=10),
        lambda c: c.update(processes=0),
        lambda c: c.update(sensitivity={"pit_loss": -1}),
        lambda c: c["env"].update(track="Nowhere"),
        lambda c: c["env"].update(team="Williams"),
        lambda c: c["env"].update(pit_loss=22.0),  # hidden since V9: only the sensitivity analysis may fix it
    ]
    validate(tiny_config())
    for mutate in cases:
        with assert_raises(ConfigError):
            validate(broken(mutate))
    folder = Path(tempfile.mkdtemp())
    (folder / "bad.json").write_text("{not json")
    for path in (folder / "bad.json", folder / "missing.json"):
        with assert_raises(ConfigError):
            load_config(path)


def test_statistics_on_known_numbers():
    s = summary([1.0, 2.0, 3.0, 6.0])
    assert (s["n"], s["mean"], s["min"], s["max"]) == (4, 3.0, 1.0, 6.0) and math.isclose(s["std"], math.sqrt(14 / 3))
    assert bootstrap_ci([5.0, 5.0, 5.0], 200, 0, 0.95) == (5.0, 5.0)
    values = [1.0, 2.0, 3.0, 4.0, 10.0]
    low, high = bootstrap_ci(values, 500, 1, 0.9)
    assert low < 4.0 < high and (low, high) == bootstrap_ci(values, 500, 1, 0.9)
    rng = random.Random(1)  # the definition: 5th and 95th percentiles of 500 seeded resample means
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(500))
    assert (low, high) == (means[25], means[475])
    result = paired({1: 10.0, 2: 12.0, 3: 9.0, 4: 7.0}, {1: 11.0, 2: 12.0, 3: 10.0, 5: 1.0}, 200, 0, 0.95)
    assert (result["n"], result["mean"], result["better"], result["worse"], result["ties"]) == (3, -2 / 3, 2, 0, 1)
    for bad in ([], [1.0]):
        with assert_raises(ValueError):
            bootstrap_ci(bad, 200, 0, 0.95)
    with assert_raises(ValueError):
        summary([])


def test_runner_is_order_preserving_parallel_safe_and_survives_failures():
    env = env_key(laps=3, team="McLaren", pit_loss=22.0, neutralisation_chance=1.0, rain_chance=0.0)
    specs = [EpisodeSpec(env, seed, policy) for seed in (1, 0) for policy in (RuleBased(), FixedOneStop(), stay_out)]
    serial, parallel = run_specs(specs, 1), run_specs(specs, 3)
    assert serial == parallel and [r["seed"] for r in serial] == [1, 1, 1, 0, 0, 0]  # input order, not sorted
    assert all(set(r) >= {"time", "reward", "stops", "penalty", "stratum"} for r in serial)
    failed = run_spec(EpisodeSpec(env, 0, Exploding()))
    assert failed["error"] == "RuntimeError: deliberate failure" and "time" not in failed
    assert stratum({"weather": object(), "incidents": [1]}) == "wet"
    assert stratum({"weather": None, "incidents": [1]}) == "neutralised"
    assert stratum({"weather": None, "incidents": []}) == "quiet"


def test_research_policies_fit_the_v7_interface():
    env = StrategyEnv(laps=3, neutralisation_chance=0.0, rain_chance=0.0)
    observation, info = env.reset(seed=0)
    for policy in (RuleBased(**{name: low for name, (low, _) in BOUNDS.items()}), FixedOneStop(), stay_out):
        action = policy(observation, info["action_mask"])
        assert isinstance(action, int) and info["action_mask"][action]


def test_cem_is_reproducible_and_skips_failed_candidates():
    def score(policies):  # synthetic objective: closer to wear_limit 0.9 is better; wear_limit > 0.95 "fails"
        return [-math.inf if p.wear_limit > 0.95 else -abs(p.wear_limit - 0.9) for p in policies]

    first = cross_entropy(score, BOUNDS, iterations=4, population=6, elites=2, seed=3)
    assert first == cross_entropy(score, BOUNDS, iterations=4, population=6, elites=2, seed=3)
    best, best_score, start_score, history, failed = first
    assert math.isclose(start_score, -0.15) and best_score >= start_score
    assert best.wear_limit <= 0.95 and len(history) == 4
    _, never, start, history, all_failed = cross_entropy(lambda ps: [-math.inf] * len(ps), BOUNDS, 2, 3, 1, 0)
    assert never == start == -math.inf and all_failed == 7  # start + 2 x 3 candidates
    assert [h["elite_mean"] for h in history] == [None, None]  # failed candidates never become elites


def test_training_rejects_candidates_whose_episodes_fail():
    original = experiment.run_specs

    def only_the_hand_set_rule_works(specs, processes):
        return [{"seed": spec.seed, "reward": -1.0} if spec.policy == RuleBased() else {"seed": spec.seed, "error": "boom"}
                for spec in specs]

    experiment.run_specs = only_the_hand_set_rule_works
    try:
        result = experiment.train(tiny_config(), "random", 0)
    finally:
        experiment.run_specs = original
    assert result["policy"] == {"wear_limit": 0.75, "neutral_from": 0.3, "neutral_to": 0.85, "final_call": 0.85}
    assert result["failed_candidates"] == 2 and result["failed_episodes"] == 2 and result["errors"] == ["boom", "boom"]


def test_verdict_applies_the_preregistered_decision_rule():
    def entry(low, high):
        return {"vs_rule_based": {"ci": [low, high], "mean": (low + high) / 2}}

    summaries = {"tuned a run 0": entry(-3, -1), "tuned a run 1": entry(-2, -0.5), "tuned a run 2": entry(-1, 1),
                 "tuned b run 0": entry(-1, -0.1), "tuned b run 1": entry(0.5, 2), "tuned b run 2": entry(-2, 3),
                 "rule-based": {}}
    result = experiment.verdict({}, summaries, ["a", "b"])
    assert (result["a"]["helps"], result["a"]["ci_below_zero"], result["a"]["ci_above_zero"]) == (True, 2, 0)
    assert (result["b"]["helps"], result["b"]["ci_below_zero"], result["b"]["ci_above_zero"]) == (False, 1, 1)
    assert math.isclose(result["a"]["mean_of_run_means"], (-2 - 1.25 + 0) / 3)


def test_experiment_runs_is_reproducible_and_stores_config_and_revision():
    path = write(tiny_config())
    out1, out2 = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    first, second = experiment.run(path, out1), experiment.run(path, out2)
    assert first["status"] == "complete" and first["failed_episodes"] == 0
    assert first["training"] == second["training"]
    assert first["evaluation"]["main"]["summaries"] == second["evaluation"]["main"]["summaries"]
    stored = json.loads((out1 / "tiny.json").read_text())
    assert stored["config"] == tiny_config() and stored["revision"]["code_digest"] == code_digest()
    assert {"git_head", "dirty"} <= set(stored["revision"]) and (out1 / "tiny.md").read_text().startswith("# Experiment")
    summaries = stored["evaluation"]["main"]["summaries"]
    assert set(summaries) == {"rule-based", "fixed one-stop", "tuned random run 0", "tuned random run 1",
                              "tuned stratified run 0", "tuned stratified run 1"}
    assert set(stored["evaluation"]["main"]["verdict"]) == {"random", "stratified"}


def test_failed_episodes_abort_the_experiment_but_keep_partial_results():
    path, out = write(tiny_config()), Path(tempfile.mkdtemp())
    original = experiment.BASELINE_POLICIES["fixed one-stop"]
    experiment.BASELINE_POLICIES["fixed one-stop"] = Exploding()
    try:
        with assert_raises(experiment.ExperimentError):
            experiment.run(path, out)
    finally:
        experiment.BASELINE_POLICIES["fixed one-stop"] = original
    stored = json.loads((out / "tiny.json").read_text())
    assert stored["status"].startswith("aborted") and stored["failed_episodes"] >= 1
    assert stored["evaluation"]["main"]["summaries"]["fixed one-stop"]["failed"] >= 1


def test_committed_results_match_the_committed_code_config_and_report():
    stored_path = Path(experiment.RESULTS) / "scenario_coverage.json"
    stored = json.loads(stored_path.read_text())
    assert stored["status"] == "complete" and stored["failed_episodes"] == 0
    assert stored["config"] == load_config(CONFIGS / "scenario_coverage.json")
    assert stored["revision"]["code_digest"] == code_digest(), "code changed since the results were produced: rerun"
    assert experiment.report(stored) == (Path(experiment.RESULTS) / "scenario_coverage.md").read_text()


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
    print("ok")
