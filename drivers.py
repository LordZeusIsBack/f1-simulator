from dataclasses import dataclass, fields

PACE_SPREAD = 0.01  # extra lap-time fraction for a pace-0 driver (1 % ≈ 0.95 s at Monza), placeholder


@dataclass(frozen=True)
class Driver:
    """Who drives the car: what the driver can do, not what the driver decides. Every field after `name` is a skill
    from 0 (weakest) to 1 (best); values are model inputs, not ratings of real drivers. Definitions and the planned
    effects of the profile-only skills: docs/phase2/p2-v1/IMPLEMENTATION.md."""
    name: str = ""
    pace: float = 1.0  # 1 = drives at the car's limit; 0 = PACE_SPREAD slower
    racecraft: float = 0.5  # general wheel-to-wheel skill: the value of attack and defence when they are not given
    attack: float | None = None  # lowers the speed advantage this driver needs to pass (traffic.required_advantage)
    defence: float | None = None  # raises the speed advantage a rival needs to pass this driver
    tyre_management: float = 0.5  # profile only until a later milestone lets the driver trade pace for tyre wear
    consistency: float = 0.5  # profile only until a later milestone adds lap-to-lap variation
    wet_weather: float = 0.5  # profile only until a later milestone models driving on low grip

    def __post_init__(self):
        for attribute in ("attack", "defence"):
            if getattr(self, attribute) is None:
                object.__setattr__(self, attribute, self.racecraft)  # frozen: set once, here
        for field in fields(self)[1:]:
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:  # NaN fails too
                raise ValueError(f"{field.name} must be a number from 0 to 1, got {value!r}")

    def time_factor(self) -> float:
        """Multiplier on the car's lap time: 1.0 for a pace-1 driver."""
        return 1 + PACE_SPREAD * (1 - self.pace)
