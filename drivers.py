from dataclasses import dataclass

PACE_SPREAD = 0.01  # extra lap-time fraction for a pace-0 driver (1 % ≈ 0.95 s at Monza), placeholder


@dataclass(frozen=True)
class Driver:
    """Who drives the car. Attributes run from 0 (weakest) to 1 (best); values are model inputs, not ratings."""
    name: str = ""
    pace: float = 1.0  # 1 = drives at the car's limit; 0 = PACE_SPREAD slower
    racecraft: float = 0.5  # wheel-to-wheel skill, used both to attack and to defend

    def __post_init__(self):
        for attribute in ("pace", "racecraft"):
            value = getattr(self, attribute)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError(f"{attribute} must be a number from 0 to 1, got {value!r}")

    def time_factor(self) -> float:
        """Multiplier on the car's lap time: 1.0 for a pace-1 driver."""
        return 1 + PACE_SPREAD * (1 - self.pace)
