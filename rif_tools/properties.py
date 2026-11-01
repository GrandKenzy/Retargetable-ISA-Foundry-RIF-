"""Small deterministic property/fuzzing helpers with no third-party dependency."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class PropertyFailure(AssertionError):
    name: str
    seed: int
    case_index: int
    case: object
    reason: str

    def __str__(self) -> str:
        return (
            f"{self.name} falló en caso {self.case_index} con seed {self.seed}: "
            f"{self.reason}; entrada={self.case!r}"
        )


def run_property(
    generator: Callable[[random.Random], T],
    predicate: Callable[[T], object],
    *,
    cases: int = 100,
    seed: int = 0,
    name: str = "property",
) -> int:
    """Run a deterministic property and return the number of cases executed."""

    if isinstance(cases, bool) or not isinstance(cases, int) or cases <= 0:
        raise ValueError("cases debe ser un entero positivo.")
    rng = random.Random(seed)
    for index in range(cases):
        case = generator(rng)
        try:
            result = predicate(case)
            if result is False:
                raise AssertionError("la propiedad devolvió False")
        except Exception as exc:
            if isinstance(exc, PropertyFailure):
                raise
            raise PropertyFailure(name, seed, index, case, str(exc) or type(exc).__name__) from exc
    return cases


def integer_cases(
    *,
    minimum: int,
    maximum: int,
    edge_values: Iterable[int] = (),
) -> Callable[[random.Random], int]:
    """Build a generator that mixes random integers with important edges."""

    if minimum > maximum:
        raise ValueError("minimum no puede ser mayor que maximum.")
    edges = tuple(value for value in edge_values if minimum <= value <= maximum)

    def generate(rng: random.Random) -> int:
        if edges and rng.randrange(4) == 0:
            return edges[rng.randrange(len(edges))]
        return rng.randint(minimum, maximum)

    return generate


__all__ = ["PropertyFailure", "integer_cases", "run_property"]
