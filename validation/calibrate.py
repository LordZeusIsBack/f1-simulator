"""Fit two parameters on the 2024 Italian GP only and write validation/config/calibrated.json.

    python3 -m validation.calibrate

- tyre_grip: bisection for the value that makes the mean qualifying-lap error of the four model cars zero.
- pit_loss: median of the measured 2024 pit losses.
2025 is never read here: it is kept for evaluation.
"""
import json
import statistics

from validation import metrics, reference
from validation.model import CONFIG, flying_laps, load_config

TRAIN_SEASON = 2024
GRIP_BRACKET = (1.0, 5.0)  # search range for tyre_grip
GRIP_TOLERANCE = 1e-4


def fit_tyre_grip(best_laps: dict[str, float], low: float = GRIP_BRACKET[0], high: float = GRIP_BRACKET[1]) -> float:
    """tyre_grip at which the model's mean qualifying error is zero. Lap time falls as grip rises, so bisection works."""
    teams = sorted(best_laps)

    def bias(grip):
        laps = flying_laps({"tyre_grip": grip}, teams)
        return metrics.mean_error([laps[t] for t in teams], [best_laps[t] for t in teams])

    if bias(low) < 0 or bias(high) > 0:
        raise ValueError(f"no zero-bias tyre_grip between {low} and {high}")
    while high - low > GRIP_TOLERANCE:
        middle = (low + high) / 2
        if bias(middle) > 0:  # model still too slow: needs more grip
            low = middle
        else:
            high = middle
    return round((low + high) / 2, 4)


def fit_pit_loss(losses: list[float]) -> float:
    if len(losses) < reference.MIN_CLEAN_LAPS:
        raise ValueError(f"need at least {reference.MIN_CLEAN_LAPS} measured stops, got {len(losses)}")
    return round(statistics.median(losses), 2)


def calibrate() -> dict:
    best = {team: time for team, (time, _) in reference.qualifying_best(TRAIN_SEASON).items()}
    losses = [stop["loss"] for stop in reference.pit_losses(TRAIN_SEASON)]
    baseline = load_config("baseline")
    return {
        "description": "Effective values fitted to the 2024 Italian GP (Monza) only; 2025 is held out for evaluation",
        "tyre_grip": fit_tyre_grip(best),
        "pit_loss": fit_pit_loss(losses),
        "method": {
            "tyre_grip": f"bisection on {list(GRIP_BRACKET)} to {GRIP_TOLERANCE}: zero mean error of the 4 model cars' "
                         f"flying laps against each team's best {TRAIN_SEASON} qualifying lap",
            "pit_loss": f"median of {len(losses)} measured {TRAIN_SEASON} stops (in-lap + out-lap - 2 x clean pace)",
        },
        "baseline": {"tyre_grip": baseline["tyre_grip"], "pit_loss": baseline["pit_loss"]},
        "trained_on": f"{TRAIN_SEASON} Italian Grand Prix, data/reference/raw/{TRAIN_SEASON}_*.json",
    }


def main() -> None:
    config = calibrate()
    (CONFIG / "calibrated.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    print(f"tyre_grip {config['tyre_grip']} (baseline {config['baseline']['tyre_grip']}), "
          f"pit_loss {config['pit_loss']} s (baseline {config['baseline']['pit_loss']} s)")


if __name__ == "__main__":
    main()
