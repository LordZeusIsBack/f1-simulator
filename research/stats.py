"""Aggregation: summaries, paired differences and seeded bootstrap confidence intervals."""
import random
import statistics


def summary(values: list[float]) -> dict:
    if not values:
        raise ValueError("no values to summarise")
    return {"n": len(values), "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0, "min": min(values), "max": max(values)}


def bootstrap_ci(values: list[float], resamples: int, seed: int, confidence: float) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean. Seeded, so the same inputs give the same interval."""
    if len(values) < 2:
        raise ValueError("a bootstrap interval needs at least two values")
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(resamples))
    tail = (1 - confidence) / 2
    return means[int(tail * resamples)], means[min(int((1 - tail) * resamples), resamples - 1)]


def paired(candidate: dict[int, float], reference: dict[int, float], resamples: int, seed: int, confidence: float) -> dict:
    """Per-seed differences candidate - reference (lower = candidate faster) on the seeds both completed."""
    seeds = sorted(set(candidate) & set(reference))
    differences = [candidate[s] - reference[s] for s in seeds]
    low, high = bootstrap_ci(differences, resamples, seed, confidence)
    return {**summary(differences), "ci": [low, high], "better": sum(d < 0 for d in differences),
            "worse": sum(d > 0 for d in differences), "ties": sum(d == 0 for d in differences)}
