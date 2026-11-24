from dataclasses import dataclass

from alignment.costs import PricedCandidate, pair_cost
from alignment.solver import AlignmentSolution
from recording.provenance import RevisionProvenance, describe_revision
from recording.revisions import FrozenRevision
from recording.validate_track import Sample


@dataclass(frozen=True, slots=True)
class WitnessPair:
    main: Sample
    secondary: Sample
    main_index: int
    secondary_index: int
    cost: int


@dataclass(frozen=True, slots=True)
class AlignmentWitness:
    provenance: RevisionProvenance
    total_cost: int
    pairs: tuple[WitnessPair, ...]


def build_witness(
    revision: FrozenRevision,
    layers: tuple[tuple[PricedCandidate, ...], ...],
    solution: AlignmentSolution,
) -> AlignmentWitness:
    indices = solution.secondary_indices
    if len(indices) != len(layers) or len(indices) != len(revision.main):
        raise ValueError('the witness must cover every main sample')
    pairs = []
    previous = -1
    for main_index, (index, layer) in enumerate(zip(indices, layers)):
        if not previous < index < len(revision.secondary):
            raise ValueError('the witness must advance in secondary order')
        priced = next((candidate for candidate in layer if candidate.secondary_index == index), None)
        main = revision.main[main_index]
        secondary = revision.secondary[index]
        cost = pair_cost(main.reading, secondary.reading)
        if priced is None or priced.main_index != main_index or priced.cost != cost:
            raise ValueError('the witness uses a pair outside the priced candidates')
        pairs.append(WitnessPair(main, secondary, main_index, index, cost))
        previous = index
    if sum(pair.cost for pair in pairs) != solution.total_cost:
        raise ValueError('the witness cost disagrees with its pairs')
    return AlignmentWitness(describe_revision(revision), solution.total_cost, tuple(pairs))
