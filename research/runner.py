"""Run many seeded episodes, in parallel if asked, without letting one failure kill the experiment."""
import hashlib
import multiprocessing
import subprocess
import traceback
from pathlib import Path
from typing import NamedTuple

from rl.env import StrategyEnv
from rl.evaluate import run_episode

ROOT = Path(__file__).resolve().parent.parent


class EpisodeSpec(NamedTuple):
    env: tuple  # sorted (key, value) pairs for StrategyEnv(**...)
    seed: int
    policy: object  # a picklable policy, e.g. RuleBased(...)


def env_key(**kwargs) -> tuple:
    return tuple(sorted(kwargs.items()))


def stratum(scenario: dict) -> str:
    """The kind of race a seed produced: 'wet' (rain), 'neutralised' (VSC/SC, no rain) or 'quiet'."""
    if scenario["weather"] is not None:
        return "wet"
    return "neutralised" if scenario["incidents"] else "quiet"


_ENVS: dict[tuple, StrategyEnv] = {}  # one environment per configuration, per process


def run_spec(spec: EpisodeSpec) -> dict:
    """One episode. Never raises: a failure comes back as {'error': ...} so the caller can count it."""
    try:
        env = _ENVS.get(spec.env) or _ENVS.setdefault(spec.env, StrategyEnv(**dict(spec.env)))
        result = run_episode(env, spec.policy, spec.seed)
        if result["truncated"]:
            raise RuntimeError("episode was truncated")
        return {**result, "stratum": stratum(env.scenario)}
    except Exception as error:  # an experiment must survive and report a bad episode
        return {"seed": spec.seed, "error": f"{type(error).__name__}: {error}",
                "trace": traceback.format_exc(limit=3)}


def run_specs(specs: list[EpisodeSpec], processes: int = 1) -> list[dict]:
    """Results in the same order as `specs`, whatever the number of processes."""
    if processes == 1 or len(specs) < 2:
        return [run_spec(spec) for spec in specs]
    with multiprocessing.get_context("fork").Pool(processes) as pool:
        return pool.map(run_spec, specs, chunksize=1)


def code_revision() -> dict:
    """Which code produced a result: git HEAD, whether the tree was dirty, and a digest of every .py file."""
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    return {"git_head": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "code_digest": code_digest()}


def code_digest() -> str:
    """sha256 over the path and bytes of every tracked-style .py file (tests excluded): pins results to code."""
    digest = hashlib.sha256()
    for path in sorted(ROOT.glob("**/*.py")):
        relative = path.relative_to(ROOT)
        if relative.parts[0].startswith(".") or relative.name.startswith("test_") or "__pycache__" in relative.parts:
            continue
        digest.update(str(relative).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()
