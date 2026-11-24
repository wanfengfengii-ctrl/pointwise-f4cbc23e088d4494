from collections.abc import Mapping
from dataclasses import dataclass

from alignment.costs import PricedCandidate


@dataclass(frozen=True, order=True, slots=True)
class AlignmentSolution:
    total_cost: int
    secondary_indices: tuple[int, ...]


def solve_alignment(
    layers: tuple[tuple[PricedCandidate, ...], ...],
    anchors: Mapping[int, int],
) -> AlignmentSolution | None:
    """Find the cheapest full alignment subject to validated source indices."""
    states = {-1: AlignmentSolution(0, ())}
    for main_index, layer in enumerate(layers):
        fixed = anchors.get(main_index)
        following = {}
        for candidate in layer:
            index = candidate.secondary_index
            if fixed is not None and index != fixed:
                continue
            prefix = min((state for end, state in states.items() if end < index), default=None)
            if prefix is not None:
                following[index] = AlignmentSolution(
                    prefix.total_cost + candidate.cost, prefix.secondary_indices + (index,),
                )
        if not following:
            return None
        states = following
    return min(states.values())
