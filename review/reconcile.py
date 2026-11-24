from dataclasses import dataclass

from intake.verify_evidence import EvidenceRow, VerifiedEvidence
from review.anchors import Anchor


@dataclass(frozen=True, slots=True)
class ReviewResult:
    total_cost: int | None
    pairs: tuple[tuple[str, str], ...] | None


def _group_segments(evidence: VerifiedEvidence) -> tuple[list[list[EvidenceRow]], list[EvidenceRow]]:
    count = len(evidence.main_ids)
    incoming = [[] for _ in evidence.main_ids]
    exits = []
    for row in evidence.rows:
        start_rank = -1 if row.start is None else row.start[0]
        end_rank = count if row.end is None else row.end[0]
        if end_rank != start_rank + 1:
            raise ValueError('evidence segment skips a public boundary')
        if row.end is None:
            exits.append(row)
        else:
            incoming[end_rank].append(row)
    return incoming, exits


def reconcile(evidence: VerifiedEvidence, anchors: tuple[Anchor, ...]) -> ReviewResult:
    """Keep the best compatible prefix for each public secondary endpoint."""
    incoming, exits = _group_segments(evidence)
    fixed = {anchor.main_index: anchor.secondary_index for anchor in anchors}
    states = {None: (0, ())}
    for index, rows in enumerate(incoming):
        following = {}
        for row in rows:
            secondary = row.end[1]
            if index in fixed and fixed[index] != secondary:
                continue
            predecessor = None if row.start is None else row.start[1]
            prefix = states.get(predecessor)
            if prefix is None:
                continue
            score = (prefix[0] + row.cost, prefix[1] + (secondary,))
            current = following.get(secondary)
            if current is None or score < current:
                following[secondary] = score
        states = following

    finished = []
    for row in exits:
        predecessor = None if row.start is None else row.start[1]
        prefix = states.get(predecessor)
        if prefix is not None:
            finished.append((prefix[0] + row.cost, prefix[1]))
    if not finished:
        return ReviewResult(None, None)
    cost, indices = min(finished)
    pairs = tuple(zip(evidence.main_ids, (evidence.secondary_ids[index] for index in indices)))
    return ReviewResult(cost, pairs)
