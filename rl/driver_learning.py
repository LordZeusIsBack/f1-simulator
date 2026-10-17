"""Baselines, tabular Q-learning and a seeded experiment for the driving environment (P2-V4).

    python3 -m rl.driver_learning            # the experiment (7 processes) -> rl/reports/driver_experiment.{json,md}
    python3 -m rl.driver_learning --smoke    # pipeline check in about a minute (not a result)

A driving policy here is policy(observation, info) -> action index, the strategist's convention with info in place of
the mask (info["action_mask"], and info["driver_observation"] for the P2-V2 rule-based drivers).
"""
import argparse
import json
import multiprocessing
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from drivers import Driver
from driving import AGGRESSIVE, BALANCED, CONSERVATIVE, DriverAction, RuleBasedDriver
from research.runner import code_revision
from research.stats import paired, summary
from rl.driver_env import ACTIONS, DriverEnv

MAINTAIN, ATTACK, DEFEND, CONSERVE = (ACTIONS.index(action) for action in DriverAction)
REPORTS = Path(__file__).resolve().parent / "reports"
SETTINGS = {
    "env": {"laps": 5, "track": "Monza", "team": "McLaren", "opponents": 3, "dt": 0.25},
    "wear_prices": [130.0, 0.0],  # main condition (the env default), then a control whose best policy is known: push
    "runs": 3, "episodes": 300, "train_seed": 0,  # run r trains on seeds train_seed + 1000 r + 0..episodes-1
    "eval_seeds": list(range(10_000, 10_030)),  # held out: never used in training
    "alpha": 0.1, "gamma": 0.9, "epsilon": [0.3, 0.02],  # learning rate, discount per decision, exploration start/end
    "bootstrap": {"resamples": 10_000, "seed": 0, "confidence": 0.95},
    "processes": 7,
}
SMOKE = {**SETTINGS, "env": {**SETTINGS["env"], "laps": 1}, "runs": 2, "episodes": 4, "eval_seeds": [10_000, 10_001]}


# ---- baselines -----------------------------------------------------------------------------------------------------

def maintain(observation, info) -> int:
    return MAINTAIN


def conserve(observation, info) -> int:
    return CONSERVE


def push(observation, info) -> int:
    """Always at the limit when allowed: ATTACK, else DEFEND, else MAINTAIN_PACE (alone, nothing faster is allowed)."""
    mask = info["action_mask"]
    return ATTACK if mask[ATTACK] else DEFEND if mask[DEFEND] else MAINTAIN


@dataclass(frozen=True)
class RuleBased:
    """Adapter: a P2-V2 RuleBasedDriver decides from the unscaled DriverObservation and the driver's skills."""
    rule: RuleBasedDriver
    driver: Driver

    def __call__(self, observation, info) -> int:
        seen = info["driver_observation"]
        return MAINTAIN if seen is None else ACTIONS.index(self.rule(seen, self.driver).action)


def baselines(driver: Driver) -> dict:
    return {"maintain": maintain, "push": push, "conserve": conserve,
            **{f"rule {rule.name}": RuleBased(rule, driver) for rule in (CONSERVATIVE, BALANCED, AGGRESSIVE)}}


# ---- tabular Q-learning ------------------------------------------------------------------------------------------

def state(observation) -> tuple:
    """The learner's view: 3 × 3 × 2 × 2 × 2 × 2 = 144 states. Gaps in s and closing speed in m/s (unscaled here)."""
    gap = observation.gap_ahead * 3.0  # GAP_SCALE
    ahead = 0 if gap >= 1.5 else 1 if gap >= 0.5 else 2  # none or far / near / close
    closing = observation.closing * 10.0  # CLOSING_SCALE
    faster = 0 if ahead == 0 or closing <= 0 else 1 if closing <= 2.0 else 2  # not / a little / clearly faster
    return (ahead, faster, int(observation.held_up), int(observation.gap_behind * 3.0 < 1.0),
            int(observation.on_straight), int(observation.drs))


class QLearner:
    """Q(s, a) table with ε-greedy exploration over allowed actions. Unvisited pairs start at 0, which is optimistic
    (every reward is ≤ 0 in practice), so training tries each allowed action; greedy play uses visited pairs only."""

    def __init__(self, alpha: float, gamma: float, seed: int):
        self.alpha, self.gamma, self.rng = alpha, gamma, random.Random(seed)
        self.q: dict[tuple, list[float]] = {}
        self.visits: dict[tuple, list[int]] = {}

    def _row(self, s):
        if s not in self.q:
            self.q[s], self.visits[s] = [0.0] * len(ACTIONS), [0] * len(ACTIONS)
        return self.q[s]

    def act(self, observation, mask, epsilon: float = 0.0) -> int:
        s, allowed = state(observation), [a for a, ok in enumerate(mask) if ok]
        if epsilon and self.rng.random() < epsilon:
            return self.rng.choice(allowed)
        row = self._row(s)
        if not epsilon:  # greedy play: only actions tried in training; untried states fall back to MAINTAIN_PACE
            allowed = [a for a in allowed if self.visits[s][a]] or [MAINTAIN]
        return max(allowed, key=lambda a: (row[a], -a))  # ties: lowest index

    def update(self, observation, action, reward, next_observation, next_mask, terminal: bool) -> None:
        s, row = state(observation), self._row(state(observation))
        future = 0.0 if terminal else max(q for q, ok in zip(self._row(state(next_observation)), next_mask) if ok)
        row[action] += self.alpha * (reward + self.gamma * future - row[action])
        self.visits[s][action] += 1

    def __call__(self, observation, info) -> int:  # a policy, like the baselines
        return self.act(observation, info["action_mask"])

    def table(self) -> dict[str, dict]:
        """Readable learned policy: per visited state, the greedy action and its visit count."""
        rows = {}
        for s in sorted(self.q):
            tried = [a for a in range(len(ACTIONS)) if self.visits[s][a]]
            if tried:
                best = max(tried, key=lambda a: (self.q[s][a], -a))
                rows[str(s)] = {"action": ACTIONS[best].name, "q": [round(v, 4) for v in self.q[s]], "visits": self.visits[s]}
        return rows


def train(env_kwargs: dict, wear_price: float, run: int, settings: dict) -> tuple[QLearner, list[float]]:
    """One training run: `episodes` episodes on seeds train_seed + 1000 × run + i. Returns the learner and the
    return of every training episode (with exploration)."""
    env = DriverEnv(wear_price=wear_price, **env_kwargs)
    learner = QLearner(settings["alpha"], settings["gamma"], seed=settings["train_seed"] + run)
    start, end = settings["epsilon"]
    episodes, returns = settings["episodes"], []
    for i in range(episodes):
        epsilon = start + (end - start) * i / max(episodes - 1, 1)
        observation, info = env.reset(seed=settings["train_seed"] + 1000 * run + i)
        total, done = 0.0, False
        while not done:
            action = learner.act(observation, info["action_mask"], epsilon)
            result = env.step(action)
            done = result.terminated or result.truncated
            learner.update(observation, action, result.reward, result.observation, result.info["action_mask"],
                           result.terminated)
            observation, info, total = result.observation, result.info, total + result.reward
        returns.append(total)
    return learner, returns


# ---- evaluation ----------------------------------------------------------------------------------------------------

def run_episode(env: DriverEnv, policy, seed: int) -> dict:
    observation, info = env.reset(seed=seed)
    total = time_lost = wear_cost = 0.0
    actions = [0] * len(ACTIONS)
    done = False
    while not done:
        action = policy(observation, info)
        actions[action] += 1
        result = env.step(action)
        observation, info = result.observation, result.info
        total, time_lost, wear_cost = total + result.reward, time_lost + info["time_lost"], wear_cost + info["wear_cost"]
        done = result.terminated or result.truncated
    return {"seed": seed, "return": total, "time_lost": time_lost, "wear_cost": wear_cost,
            "finish_time": info["finish_time"], "position": info["position"], "passes": info["passes"],
            "passed_by": info["passed_by"], "tyre_wear": info["tyre_wear"], "clipped": info["clipped"],
            "actions": dict(zip((a.name for a in ACTIONS), actions))}


def _job(job):
    kind, env_kwargs, wear_price, payload, settings = job
    if kind == "train":
        learner, returns = train(env_kwargs, wear_price, payload, settings)
        return learner, returns
    policy, seeds = payload
    env = DriverEnv(wear_price=wear_price, **env_kwargs)
    return [run_episode(env, policy, seed) for seed in seeds]


def _map(jobs, processes: int):
    if processes == 1 or len(jobs) < 2:
        return [_job(job) for job in jobs]
    with multiprocessing.get_context("fork").Pool(processes) as pool:
        return pool.map(_job, jobs)


def experiment(settings: dict = SETTINGS) -> dict:
    """Train `runs` learners per wear price, then evaluate them and every baseline on the held-out seeds."""
    env_kwargs, processes = settings["env"], settings["processes"]
    driver = DriverEnv(**env_kwargs).driver
    record = {"settings": settings, "revision": code_revision(), "conditions": {}}
    for price in settings["wear_prices"]:
        trained = _map([("train", env_kwargs, price, run, settings) for run in range(settings["runs"])], processes)
        policies = {**baselines(driver), **{f"Q-learning run {run}": learner for run, (learner, _) in enumerate(trained)}}
        seeds = settings["eval_seeds"]
        chunks = [seeds[i::processes] for i in range(processes)] if processes > 1 else [seeds]
        jobs = [("eval", env_kwargs, price, (policy, chunk), settings) for policy in policies.values() for chunk in chunks if chunk]
        results = iter(_map(jobs, processes))
        episodes = {name: sorted((e for chunk in chunks if chunk for e in next(results)), key=lambda e: e["seed"])
                    for name in policies}
        record["conditions"][str(price)] = {
            "training": {f"run {run}": {"returns": returns, "policy": learner.table()}
                         for run, (learner, returns) in enumerate(trained)},
            "episodes": episodes,
            "summary": summarise(episodes, settings["bootstrap"]),
        }
    return record


def summarise(episodes: dict[str, list[dict]], bootstrap: dict) -> dict:
    """Per policy: mean return and its parts; paired difference in return to the best baseline (higher = better)."""
    names = [name for name in episodes if not name.startswith("Q-learning")]
    best = max(names, key=lambda name: statistics.mean(e["return"] for e in episodes[name]))
    reference = {e["seed"]: -e["return"] for e in episodes[best]}
    rows = {}
    for name, eps in episodes.items():
        rows[name] = {
            "return": summary([e["return"] for e in eps]),
            "time_lost": statistics.mean(e["time_lost"] for e in eps),
            "wear_cost": statistics.mean(e["wear_cost"] for e in eps),
            "finish_time": statistics.mean(e["finish_time"] for e in eps),
            "position": statistics.mean(e["position"] for e in eps),
            "passes": statistics.mean(e["passes"] for e in eps),
            "clipped": sum(e["clipped"] for e in eps),
            # cost = −return, so a negative difference means fewer seconds lost than the best baseline
            "vs_best_baseline": paired({e["seed"]: -e["return"] for e in eps}, reference, **bootstrap),
        }
    return {"best_baseline": best, "policies": rows}


# ---- report --------------------------------------------------------------------------------------------------------

def report(record: dict) -> str:
    s = record["settings"]
    lines = [
        "# Driver RL experiment report (generated)",
        "",
        "Generated by `python3 -m rl.driver_learning`. Do not edit by hand. Cost = seconds lost against the ideal lap "
        "+ wear price × tyre wear added (= −return); lower is better.",
        "",
        "## Settings",
        "",
        f"- Environment: `DriverEnv({', '.join(f'{k}={v!r}' for k, v in s['env'].items())})`, default driver "
        f"(all skills 0.5), calibrated grip, {s['env']['opponents']} rivals with random pace and racecraft, random grid "
        "slot, medium tyres, dry, no race control.",
        f"- Tabular Q-learning: {s['runs']} runs × {s['episodes']} training episodes per wear price; α = {s['alpha']}, "
        f"γ = {s['gamma']}, ε {s['epsilon'][0]} → {s['epsilon'][1]} (linear). Training seeds: run r uses "
        f"{s['train_seed']} + 1000 r + 0..{s['episodes'] - 1}.",
        f"- Evaluation: {len(s['eval_seeds'])} held-out seeds ({s['eval_seeds'][0]}–{s['eval_seeds'][-1]}), the same "
        f"for every policy; paired differences with a {s['bootstrap']['confidence']:.0%} bootstrap interval "
        f"({s['bootstrap']['resamples']} resamples, seed {s['bootstrap']['seed']}).",
        f"- Code: git HEAD `{record['revision']['git_head']}`, dirty tree: {record['revision']['dirty']}.",
    ]
    for price, condition in record["conditions"].items():
        summ = condition["summary"]
        best = summ["best_baseline"]
        lines += [
            "",
            f"## Wear price {float(price):g} s per unit of wear",
            "",
            "| Policy | Mean cost (s) | Std | Time lost (s) | Wear cost (s) | Finish (s) | Position | Passes | Clipped "
            f"| vs {best}: mean [95 % CI] (s) | Better / worse |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, row in summ["policies"].items():
            d = row["vs_best_baseline"]
            lines.append(f"| {name} | {-row['return']['mean']:.2f} | {row['return']['std']:.2f} | {row['time_lost']:.2f} "
                         f"| {row['wear_cost']:.2f} | {row['finish_time']:.2f} | {row['position']:.2f} | {row['passes']:.2f} "
                         f"| {row['clipped']} | {d['mean']:+.2f} [{d['ci'][0]:+.2f}, {d['ci'][1]:+.2f}] "
                         f"| {d['better']} / {d['worse']} |")
        lines += ["", "Training (mean return of the first and last 10% of episodes, with exploration):", ""]
        for run, data in condition["training"].items():
            r = data["returns"]
            k = max(1, len(r) // 10)
            lines.append(f"- {run}: {statistics.mean(r[:k]):.2f} → {statistics.mean(r[-k:]):.2f}; "
                         f"{len(data['policy'])} states visited")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--smoke", action="store_true", help="tiny run to check the pipeline (not a result)")
    args = parser.parse_args()
    record = experiment(SMOKE if args.smoke else SETTINGS)
    text = report(record)
    if not args.smoke:
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "driver_experiment.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
        (REPORTS / "driver_experiment.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
