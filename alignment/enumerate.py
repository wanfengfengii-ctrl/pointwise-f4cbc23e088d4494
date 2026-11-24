from dataclasses import dataclass

from alignment.candidates import build_candidates
from alignment.costs import price_candidates
from recording.revisions import FrozenRevision


@dataclass(frozen=True, order=True, slots=True)
class FeasiblePairing:
    total_cost: int
    secondary_indices: tuple[int, ...]


def enumerate_pairings(revision: FrozenRevision) -> tuple[FeasiblePairing, ...]:
    """Enumerate every complete, strictly increasing secondary placement.

    Hidden beats keep their position in each tuple and still contribute cost;
    only the aggregate whole-pairing total leaves the source station.
    """
    layers = price_candidates(revision, build_candidates(revision))
    states: dict[int, list[tuple[int, tuple[int, ...]]]] = {-1: [(0, ())]}
    for layer in layers:
        following: dict[int, list[tuple[int, tuple[int, ...]]]] = {}
        for end, prefixes in states.items():
            for candidate in layer:
                index = candidate.secondary_index
                if index <= end:
                    continue
                for cost, indices in prefixes:
                    following.setdefault(index, []).append(
                        (cost + candidate.cost, indices + (index,))
                    )
        if not following:
            return ()
        states = following

    pairings = {
        indices: cost
        for prefixes in states.values()
        for cost, indices in prefixes
    }
    return tuple(
        FeasiblePairing(cost, indices)
        for indices, cost in sorted(
            pairings.items(), key=lambda item: (item[0], item[1])
        )
    )
