"""Error metrics. Positive error = the model is higher (slower, longer) than the reference."""


def error(model: float, reference: float) -> float:
    return model - reference


def relative_error(model: float, reference: float) -> float:
    if reference == 0:
        raise ValueError("relative error needs a non-zero reference")
    return (model - reference) / reference


def _pairs(model: list[float], reference: list[float]) -> list[tuple[float, float]]:
    if len(model) != len(reference) or not model:
        raise ValueError(f"need equal, non-empty lists, got {len(model)} and {len(reference)}")
    return list(zip(model, reference))


def mean_error(model: list[float], reference: list[float]) -> float:
    """Bias: average signed error."""
    pairs = _pairs(model, reference)
    return sum(m - r for m, r in pairs) / len(pairs)


def mean_absolute_error(model: list[float], reference: list[float]) -> float:
    pairs = _pairs(model, reference)
    return sum(abs(m - r) for m, r in pairs) / len(pairs)


def mean_absolute_percentage_error(model: list[float], reference: list[float]) -> float:
    pairs = _pairs(model, reference)
    return 100 * sum(abs(relative_error(m, r)) for m, r in pairs) / len(pairs)


def max_absolute_error(model: list[float], reference: list[float]) -> float:
    return max(abs(m - r) for m, r in _pairs(model, reference))
