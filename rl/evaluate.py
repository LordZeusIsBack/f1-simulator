"""Run policies over the same seeded episodes and summarise the results with their variability.

    python3 -m rl.evaluate --laps 53 --seeds 20
"""
import argparse
import statistics

from rl.env import StrategyEnv
from rl.policies import FixedOneStop, RandomPolicy, RuleBased, stay_out

BASELINES = {
    "stay out": lambda seed: stay_out,
    "fixed one-stop": lambda seed: FixedOneStop(),
    "rule-based": lambda seed: RuleBased(),
    "random (10 % pit)": lambda seed: RandomPolicy(seed),
}


def run_episode(env: StrategyEnv, policy, seed: int) -> dict:
    observation, info = env.reset(seed=seed)
    total, done = 0.0, False
    while not done:
        result = env.step(policy(observation, info["action_mask"]))
        observation, info, total = result.observation, result.info, total + result.reward
        done = result.terminated or result.truncated
    return {"seed": seed, "reward": total, "time": info["total_time"], "stops": len(info["pit_stops"]),
            "penalty": info["penalty_time"], "truncated": result.truncated}


def compare(policies: dict, seeds, **env_kwargs) -> dict[str, list[dict]]:
    """Every policy plays the same episodes (same seeds, so the same scenarios)."""
    env = StrategyEnv(**env_kwargs)
    return {name: [run_episode(env, make(seed), seed) for seed in seeds] for name, make in policies.items()}


def summarise(results: dict[str, list[dict]], baseline: str) -> list[dict]:
    """Per policy: race time mean, sample std, min, max; stops; penalties; paired difference to `baseline`."""
    reference = [episode["time"] for episode in results[baseline]]
    rows = []
    for name, episodes in results.items():
        times = [episode["time"] for episode in episodes]
        differences = [t - r for t, r in zip(times, reference)]
        rows.append({
            "policy": name,
            "mean": statistics.mean(times),
            "std": statistics.stdev(times) if len(times) > 1 else 0.0,
            "min": min(times),
            "max": max(times),
            "stops": statistics.mean(episode["stops"] for episode in episodes),
            "penalised": sum(episode["penalty"] > 0 for episode in episodes),
            "diff_mean": statistics.mean(differences),
            "diff_std": statistics.stdev(differences) if len(differences) > 1 else 0.0,
            "better": sum(d < 0 for d in differences),
            "worse": sum(d > 0 for d in differences),
        })
    return rows


def table(rows: list[dict], baseline: str, episodes: int) -> str:
    lines = [
        f"| Policy | Mean race time (s) | Std (s) | Min | Max | Mean stops | Penalised | vs {baseline}: mean ± std (s) | Better / worse |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['policy']} | {r['mean']:.1f} | {r['std']:.1f} | {r['min']:.1f} | {r['max']:.1f} | {r['stops']:.2f} "
                     f"| {r['penalised']}/{episodes} | {r['diff_mean']:+.1f} ± {r['diff_std']:.1f} | {r['better']} / {r['worse']} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--laps", type=int, default=53)
    parser.add_argument("--seeds", type=int, default=20, help="evaluate on seeds 100 .. 100 + N - 1")
    args = parser.parse_args()
    seeds = range(100, 100 + args.seeds)
    rows = summarise(compare(BASELINES, seeds, laps=args.laps), "rule-based")
    print(table(rows, "rule-based", args.seeds))


if __name__ == "__main__":
    main()
