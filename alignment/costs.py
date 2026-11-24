from dataclasses import dataclass

from alignment.candidates import Candidate
from recording.revisions import FrozenRevision


@dataclass(frozen=True, slots=True)
class PricedCandidate:
    main_index: int
    secondary_index: int
    cost: int


def pair_cost(main_reading: int, secondary_reading: int) -> int:
    return abs(main_reading - secondary_reading)


def price_candidates(
    revision: FrozenRevision, layers: tuple[tuple[Candidate, ...], ...],
) -> tuple[tuple[PricedCandidate, ...], ...]:
    priced = []
    for layer in layers:
        priced.append(tuple(
            PricedCandidate(
                candidate.main_index,
                candidate.secondary_index,
                pair_cost(
                    revision.main[candidate.main_index].reading,
                    revision.secondary[candidate.secondary_index].reading,
                ),
            )
            for candidate in layer
        ))
    return tuple(priced)
