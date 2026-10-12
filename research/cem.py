"""Cross-entropy method over RuleBased's thresholds, with batched scoring so a whole population runs in parallel."""
import math
import random
import statistics
from dataclasses import fields

from rl.policies import RuleBased


def cross_entropy(score_batch, bounds: dict, iterations: int, population: int, elites: int, seed: int):
    """Start at the hand-set RuleBased; return (best policy, its score, hand-set score, history, failed candidates).

    `score_batch(policies) -> list of scores`; a score of -inf marks a candidate whose episodes failed."""
    rng = random.Random(seed)
    names = [f.name for f in fields(RuleBased)]
    mean = list(RuleBased().as_vector())
    std = [(bounds[n][1] - bounds[n][0]) / 4 for n in names]
    best = RuleBased()
    [best_score] = score_batch([best])
    start_score, history, failed = best_score, [], int(best_score == -math.inf)
    for iteration in range(1, iterations + 1):
        candidates = [RuleBased(**{n: round(min(max(rng.gauss(m, s), bounds[n][0]), bounds[n][1]), 3)
                                   for n, m, s in zip(names, mean, std)}) for _ in range(population)]
        scores = score_batch(candidates)
        failed += sum(score == -math.inf for score in scores)
        ranked = sorted(zip(scores, range(population)), key=lambda pair: (-pair[0], pair[1]))  # stable on ties
        top = [(score, candidates[i]) for score, i in ranked[:elites] if score > -math.inf]
        if top and top[0][0] > best_score:
            best_score, best = top[0]
        if top:
            vectors = [policy.as_vector() for _, policy in top]
            mean = [statistics.mean(column) for column in zip(*vectors)]
            std = [max(statistics.pstdev(column), 0.02 * (bounds[n][1] - bounds[n][0]))
                   for n, column in zip(names, zip(*vectors))]
        history.append({"iteration": iteration, "best_score": best_score,
                        "elite_mean": statistics.mean(s for s, _ in top) if top else None})
    return best, best_score, start_score, history, failed
