from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from recording.revisions import FrozenRevision


@dataclass(frozen=True, slots=True)
class Candidate:
    main_index: int
    secondary_index: int


def build_candidates(revision: FrozenRevision) -> tuple[tuple[Candidate, ...], ...]:
    """Build one candidate layer per main sample, including empty layers."""
    left, right = revision.window
    sequence = [sample.sequence for sample in revision.secondary]
    layers = []
    for main_index, sample in enumerate(revision.main):
        first = bisect_left(sequence, sample.sequence - left)
        stop = bisect_right(sequence, sample.sequence + right)
        layers.append(tuple(Candidate(main_index, index) for index in range(first, stop)))
    return tuple(layers)
