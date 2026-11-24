from alignment.costs import PricedCandidate
from issue.disclosure import Disclosure


Layers = tuple[tuple[PricedCandidate, ...], ...]
Endpoint = tuple[int, int] | None
Evidence = list[tuple[Endpoint, Endpoint, int]]


def _walk(layers: Layers, start: int, stop: int, previous: int) -> dict[int, int]:
    """Price a complete segment from a fixed predecessor to each reachable end."""
    costs = {previous: 0}
    for index in range(start, stop):
        following = {}
        for candidate in layers[index]:
            end = candidate.secondary_index
            prefix = min((cost for before, cost in costs.items() if before < end), default=None)
            if prefix is not None:
                following[end] = prefix + candidate.cost
        costs = following
        if not costs:
            break
    return costs


def build_evidence(layers: Layers, disclosure: Disclosure) -> Evidence:
    """Eliminate hidden samples while retaining fixed-endpoint continuation costs.

    An arc owns the beats strictly after its start through its destination.
    A missing start or destination denotes the boundary of the recording.
    """
    public = disclosure.main_indices
    rows = []
    if not public:
        cost = min(_walk(layers, 0, len(layers), -1).values(), default=None)
        if cost is not None:
            rows.append((None, None, cost))
        return rows

    head = _walk(layers, 0, public[0] + 1, -1)
    for secondary, cost in head.items():
        rows.append((None, (0, secondary), cost))

    for rank, (left, right) in enumerate(zip(public, public[1:])):
        for candidate in layers[left]:
            start = candidate.secondary_index
            continuations = _walk(layers, left + 1, right + 1, start)
            for end, cost in continuations.items():
                rows.append(((rank, start), (rank + 1, end), cost))

    last = public[-1]
    for candidate in layers[last]:
        start = candidate.secondary_index
        finishes = _walk(layers, last + 1, len(layers), start)
        cost = min(finishes.values(), default=None)
        if cost is not None:
            rows.append(((len(public) - 1, start), None, cost))
    return rows
