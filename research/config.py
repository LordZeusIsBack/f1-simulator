"""Load and validate a research experiment configuration (JSON). Anything unexpected is a ConfigError."""
import json
from dataclasses import fields
from pathlib import Path

from cars import CARS
from rl.policies import RuleBased
from tracks import CIRCUITS

BASELINES = ("rule-based", "fixed one-stop", "stay out")
SEED_STRIDE = 7919  # CEM run r trains on seed + r * SEED_STRIDE, so every run sees different races
_TOP = {"name", "question", "decision_rule", "laps", "env", "designs", "cem", "evaluation", "sensitivity",
        "statistics", "processes", "max_failed_episodes"}
_ENV = {"team", "track"}  # pit loss is hidden and random per race (rl.env, V9); sensitivity may fix it
_SOURCE = {"neutralisation_chance", "rain_chance", "seeds"}
_CEM = {"runs", "iterations", "population", "elites", "bounds"}
_EVALUATION = {"neutralisation_chance", "rain_chance", "seeds_from", "episodes", "baselines"}
_STATISTICS = {"bootstrap_resamples", "bootstrap_seed", "confidence"}


class ConfigError(ValueError):
    pass


def _keys(section: dict, allowed: set, where: str) -> None:
    if not isinstance(section, dict):
        raise ConfigError(f"{where} must be an object")
    if set(section) != allowed:
        missing, extra = allowed - set(section), set(section) - allowed
        raise ConfigError(f"{where}: missing {sorted(missing)}, unknown {sorted(extra)}")


def _int(value, where: str, low: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < low:
        raise ConfigError(f"{where} must be an integer >= {low}, got {value!r}")
    return value


def _chance(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ConfigError(f"{where} must be a number in [0, 1], got {value!r}")
    return value


def load_config(path: Path) -> dict:
    try:
        config = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ConfigError(f"no config file {path}") from None
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not valid JSON: {error}") from None
    validate(config)
    return config


def validate(config: dict) -> None:
    _keys(config, _TOP, "config")
    for text in ("name", "question", "decision_rule"):
        if not isinstance(config[text], str) or not config[text].strip():
            raise ConfigError(f"{text} must be a non-empty string")
    _int(config["laps"], "laps", 2)
    _keys(config["env"], _ENV, "env")
    if config["env"]["team"] not in CARS or config["env"]["track"] not in CIRCUITS:
        raise ConfigError(f"env needs a team from {sorted(CARS)} and a track from {sorted(CIRCUITS)}")

    designs = config["designs"]
    if not isinstance(designs, dict) or len(designs) < 2:
        raise ConfigError("designs must name at least two training designs to compare")
    budgets, train_seeds = set(), []
    for name, sources in designs.items():
        if not isinstance(sources, list) or not sources:
            raise ConfigError(f"design {name!r} must be a non-empty list of episode sources")
        for i, source in enumerate(sources):
            where = f"design {name!r} source {i}"
            _keys(source, _SOURCE, where)
            _chance(source["neutralisation_chance"], f"{where}.neutralisation_chance")
            _chance(source["rain_chance"], f"{where}.rain_chance")
            if not isinstance(source["seeds"], list) or not source["seeds"]:
                raise ConfigError(f"{where}.seeds must be a non-empty list")
            train_seeds += [_int(seed, f"{where} seed") for seed in source["seeds"]]
        budgets.add(sum(len(source["seeds"]) for source in sources))
    if len(budgets) != 1:
        raise ConfigError(f"designs must have the same number of training episodes, got {sorted(budgets)}")

    cem = config["cem"]
    _keys(cem, _CEM, "cem")
    if not isinstance(cem["runs"], list) or not cem["runs"]:
        raise ConfigError("cem.runs must be a non-empty list of seeds")
    for seed in cem["runs"]:
        _int(seed, "cem run seed")
    _int(cem["iterations"], "cem.iterations", 1)
    _int(cem["population"], "cem.population", 1)
    if not 1 <= _int(cem["elites"], "cem.elites", 1) <= cem["population"]:
        raise ConfigError("cem.elites must be between 1 and cem.population")
    names = [f.name for f in fields(RuleBased)]
    _keys(cem["bounds"], set(names), "cem.bounds")
    start = RuleBased()
    for name in names:
        low, high = cem["bounds"][name] if isinstance(cem["bounds"][name], list) and len(cem["bounds"][name]) == 2 else (None, None)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (low, high)) or not low < high:
            raise ConfigError(f"cem.bounds.{name} must be [low, high] with low < high")
        if not low <= getattr(start, name) <= high:
            raise ConfigError(f"cem.bounds.{name} must contain the hand-set start value {getattr(start, name)}")

    evaluation = config["evaluation"]
    _keys(evaluation, _EVALUATION, "evaluation")
    _chance(evaluation["neutralisation_chance"], "evaluation.neutralisation_chance")
    _chance(evaluation["rain_chance"], "evaluation.rain_chance")
    _int(evaluation["episodes"], "evaluation.episodes", 2)
    first = _int(evaluation["seeds_from"], "evaluation.seeds_from")
    held_out = range(first, first + evaluation["episodes"])
    if any(seed + run * SEED_STRIDE in held_out for seed in train_seeds for run in cem["runs"]):
        raise ConfigError("a training seed (after the per-run shift) falls among the evaluation seeds")
    if "rule-based" not in evaluation["baselines"] or set(evaluation["baselines"]) - set(BASELINES):
        raise ConfigError(f"evaluation.baselines must include 'rule-based' and only use {BASELINES}")

    sensitivity = config["sensitivity"]
    if not isinstance(sensitivity, dict) or set(sensitivity) - {"pit_loss"}:
        raise ConfigError("sensitivity must be an object with at most a pit_loss value")
    if "pit_loss" in sensitivity and (isinstance(sensitivity["pit_loss"], bool)
                                      or not isinstance(sensitivity["pit_loss"], (int, float)) or sensitivity["pit_loss"] < 0):
        raise ConfigError("sensitivity.pit_loss must be a number >= 0")

    statistics = config["statistics"]
    _keys(statistics, _STATISTICS, "statistics")
    _int(statistics["bootstrap_resamples"], "statistics.bootstrap_resamples", 100)
    _int(statistics["bootstrap_seed"], "statistics.bootstrap_seed")
    if isinstance(statistics["confidence"], bool) or not isinstance(statistics["confidence"], float) \
            or not 0.5 < statistics["confidence"] < 1:
        raise ConfigError("statistics.confidence must be a float in (0.5, 1)")
    _int(config["processes"], "processes", 1)
    _int(config["max_failed_episodes"], "max_failed_episodes")
