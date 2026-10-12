"""V8 experiment: does the scenario mix of the training races decide whether tuning beats the hand-set rule?

    python3 -m research.scenario_coverage                      # research/configs/scenario_coverage.json
    python3 -m research.scenario_coverage research/configs/smoke.json

Writes research/results/<name>.json (everything, incl. per-episode results, config and code revision) and
research/results/<name>.md (the report). The verdict is computed from the decision rule in the config.
"""
import json
import math
import platform
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

from research.cem import cross_entropy
from research.config import SEED_STRIDE, load_config
from research.runner import EpisodeSpec, code_revision, env_key, run_specs
from research.stats import paired, summary
from rl.policies import FixedOneStop, RuleBased, stay_out

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "configs" / "scenario_coverage.json"
RESULTS = HERE / "results"
BASELINE_POLICIES = {"rule-based": RuleBased(), "fixed one-stop": FixedOneStop(), "stay out": stay_out}


class ExperimentError(RuntimeError):
    pass


def training_specs(config: dict, design: str, run: int, policy) -> list[EpisodeSpec]:
    """The design's training episodes. Each CEM run shifts the seeds, so runs differ in races, not just in sampling."""
    common = dict(laps=config["laps"], **config["env"])
    return [EpisodeSpec(env_key(**common, neutralisation_chance=source["neutralisation_chance"],
                                rain_chance=source["rain_chance"]), seed + run * SEED_STRIDE, policy)
            for source in config["designs"][design] for seed in source["seeds"]]


def train(config: dict, design: str, run: int) -> dict:
    failures = []

    def score_batch(policies):
        specs = [spec for policy in policies for spec in training_specs(config, design, run, policy)]
        results = run_specs(specs, config["processes"])
        failures.extend(r for r in results if "error" in r)
        per_policy = len(specs) // len(policies)
        scores = []
        for i in range(len(policies)):
            chunk = results[i * per_policy:(i + 1) * per_policy]
            scores.append(-math.inf if any("error" in r for r in chunk) else statistics.mean(r["reward"] for r in chunk))
        return scores

    cem = config["cem"]
    best, best_score, start_score, history, failed = cross_entropy(score_batch, cem["bounds"], cem["iterations"],
                                                                   cem["population"], cem["elites"], run)
    return {"design": design, "run": run, "policy": asdict(best), "train_score": best_score,
            "hand_set_train_score": start_score, "history": history, "failed_candidates": failed,
            "failed_episodes": len(failures), "errors": [f["error"] for f in failures][:5]}


def evaluate(config: dict, policies: dict, pit_loss: float | None) -> dict[str, list[dict]]:
    """Every policy on the same held-out seeds of the evaluation distribution. pit_loss None: hidden and random."""
    evaluation = config["evaluation"]
    fixed = {} if pit_loss is None else {"pit_loss": pit_loss}
    env = env_key(laps=config["laps"], **config["env"], **fixed,
                  neutralisation_chance=evaluation["neutralisation_chance"], rain_chance=evaluation["rain_chance"])
    seeds = range(evaluation["seeds_from"], evaluation["seeds_from"] + evaluation["episodes"])
    names = list(policies)
    results = run_specs([EpisodeSpec(env, seed, policies[name]) for name in names for seed in seeds], config["processes"])
    n = len(seeds)
    return {name: results[i * n:(i + 1) * n] for i, name in enumerate(names)}


def aggregate(config: dict, episodes: dict[str, list[dict]]) -> dict:
    stats = config["statistics"]
    times = {name: {r["seed"]: r["time"] for r in rs if "error" not in r} for name, rs in episodes.items()}
    strata = {r["seed"]: r["stratum"] for rs in episodes.values() for r in rs if "error" not in r}
    reference = times["rule-based"]
    out = {}
    for name, own in times.items():
        entry = {"race_time": summary(list(own.values())), "failed": sum("error" in r for r in episodes[name])}
        if name != "rule-based":
            entry["vs_rule_based"] = paired(own, reference, stats["bootstrap_resamples"], stats["bootstrap_seed"],
                                            stats["confidence"])
            entry["by_stratum"] = {}
            for kind in ("quiet", "neutralised", "wet"):
                seeds = [s for s in own if strata.get(s) == kind and s in reference]
                if seeds:
                    entry["by_stratum"][kind] = {"n": len(seeds), "mean_diff": statistics.mean(own[s] - reference[s] for s in seeds)}
        out[name] = entry
    return out


def verdict(config: dict, summaries: dict, designs: list[str]) -> dict:
    """Decision rule: a design 'helps' if, in at least 2 of its runs (or all, if fewer than 2), the paired CI is < 0."""
    result = {}
    for design in designs:
        runs = [entry for name, entry in summaries.items() if name.startswith(f"tuned {design} ")]
        below = sum(entry["vs_rule_based"]["ci"][1] < 0 for entry in runs)
        above = sum(entry["vs_rule_based"]["ci"][0] > 0 for entry in runs)
        needed = min(2, len(runs))
        result[design] = {"runs": len(runs), "ci_below_zero": below, "ci_above_zero": above,
                          "helps": below >= needed,
                          "mean_of_run_means": statistics.mean(e["vs_rule_based"]["mean"] for e in runs),
                          "std_of_run_means": statistics.stdev([e["vs_rule_based"]["mean"] for e in runs]) if len(runs) > 1 else 0.0}
    return result


def run(config_path: Path = DEFAULT_CONFIG, results_dir: Path = RESULTS) -> dict:
    config = load_config(config_path)
    started = time.time()
    path = Path(config_path).resolve()
    shown = path.relative_to(HERE.parent) if path.is_relative_to(HERE.parent) else path  # repo-relative when possible
    record = {"config": config, "config_path": str(shown),
              "revision": code_revision(), "python": platform.python_version(), "status": "running"}
    trained = [train(config, design, run_seed) for design in config["designs"] for run_seed in config["cem"]["runs"]]
    record["training"] = trained
    policies = {name: BASELINE_POLICIES[name] for name in config["evaluation"]["baselines"]}
    policies.update({f"tuned {t['design']} run {t['run']}": RuleBased(**t["policy"]) for t in trained})
    analyses = {"main": None}
    if "pit_loss" in config["sensitivity"]:
        analyses["sensitivity"] = config["sensitivity"]["pit_loss"]
    record["evaluation"] = {}
    failed = sum(t["failed_episodes"] for t in trained)
    for analysis, pit_loss in analyses.items():
        episodes = evaluate(config, policies, pit_loss)
        failed += sum("error" in r for rs in episodes.values() for r in rs)
        summaries = aggregate(config, episodes)
        record["evaluation"][analysis] = {"pit_loss": pit_loss, "episodes": episodes, "summaries": summaries,
                                          "verdict": verdict(config, summaries, list(config["designs"]))}
    record["failed_episodes"] = failed
    record["wall_time_s"] = round(time.time() - started, 1)
    record["status"] = "complete" if failed <= config["max_failed_episodes"] else "aborted: too many failed episodes"
    save(record, results_dir)
    if record["status"] != "complete":
        raise ExperimentError(f"{failed} failed episodes (limit {config['max_failed_episodes']}); partial results saved")
    return record


def save(record: dict, results_dir: Path = RESULTS) -> None:
    results_dir.mkdir(exist_ok=True)
    name = record["config"]["name"]
    text = json.dumps(record, indent=1, sort_keys=True, default=str) + "\n"
    (results_dir / f"{name}.json").write_text(text)
    (results_dir / f"{name}.md").write_text(report(json.loads(text)))  # rendered from exactly what is stored


def report(record: dict) -> str:
    config, revision = record["config"], record["revision"]
    lines = [
        f"# Experiment report: {config['name']} (generated)",
        "",
        f"Generated by `python3 -m research.scenario_coverage {record['config_path']}`. Do not edit by hand.",
        "",
        f"- Question: {config['question']}",
        f"- Decision rule (fixed before running): {config['decision_rule']}",
        f"- Status: **{record['status']}**; failed episodes: {record['failed_episodes']}; wall time {record['wall_time_s']} s",
        f"- Code: git HEAD `{revision['git_head']}`, dirty tree: {revision['dirty']}, code digest `{revision['code_digest'][:16]}`",
        f"- Python {record['python']}; {config['processes']} processes; {config['laps']} laps; "
        f"env {json.dumps(config['env'], sort_keys=True)}",
        "",
        "## Training (each run: CEM from the hand-set thresholds; score = mean reward on the design's races)",
        "",
        "| Design | Run | Hand-set score | Tuned score | Tuned thresholds (wear, neutral from-to, final call) | Failed candidates |",
        "|---|---|---|---|---|---|",
    ]
    for t in record["training"]:
        p = t["policy"]
        lines.append(f"| {t['design']} | {t['run']} | {t['hand_set_train_score']:.4f} | {t['train_score']:.4f} | "
                     f"{p['wear_limit']}, {p['neutral_from']}-{p['neutral_to']}, {p['final_call']} | {t['failed_candidates']} |")
    for analysis, block in record["evaluation"].items():
        evaluation = config["evaluation"]
        pit_loss = "hidden, random per race" if block["pit_loss"] is None else f"fixed at {block['pit_loss']} s"
        lines += [
            "",
            f"## Evaluation: {analysis} (pit loss {pit_loss}; seeds {evaluation['seeds_from']}-"
            f"{evaluation['seeds_from'] + evaluation['episodes'] - 1}; VSC/SC chance {evaluation['neutralisation_chance']}, "
            f"rain chance {evaluation['rain_chance']})",
            "",
            "| Policy | Race time mean ± std (s) | vs rule-based: mean ± std (s) | 95 % bootstrap CI | Better / worse / tie | quiet / neutralised / wet mean diff (s) |",
            "|---|---|---|---|---|---|",
        ]
        for name in sorted(block["summaries"], key=lambda n: (n != "rule-based", n)):  # reference first
            entry = block["summaries"][name]
            rt = entry["race_time"]
            if name == "rule-based":
                lines.append(f"| {name} | {rt['mean']:.1f} ± {rt['std']:.1f} | — | — | — | — |")
                continue
            v, strata = entry["vs_rule_based"], entry["by_stratum"]
            by = " / ".join(f"{strata[k]['mean_diff']:+.1f} (n={strata[k]['n']})" if k in strata else "—"
                            for k in ("quiet", "neutralised", "wet"))
            lines.append(f"| {name} | {rt['mean']:.1f} ± {rt['std']:.1f} | {v['mean']:+.2f} ± {v['std']:.2f} | "
                         f"[{v['ci'][0]:+.2f}, {v['ci'][1]:+.2f}] | {v['better']} / {v['worse']} / {v['ties']} | {by} |")
        lines += ["", "| Design | Runs | CI below 0 | CI above 0 | Mean of run means (s) | Std of run means (s) | Helps (decision rule) |",
                  "|---|---|---|---|---|---|---|"]
        for design, v in block["verdict"].items():
            lines.append(f"| {design} | {v['runs']} | {v['ci_below_zero']} | {v['ci_above_zero']} | "
                         f"{v['mean_of_run_means']:+.2f} | {v['std_of_run_means']:.2f} | {'yes' if v['helps'] else 'no'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG)
