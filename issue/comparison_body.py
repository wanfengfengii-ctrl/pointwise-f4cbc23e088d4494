import json

from alignment.enumerate import FeasiblePairing
from recording.revisions import FrozenRevision


COMPARISON_BODY_FIELDS = (
    'group_id', 'run_id', 'revision_id', 'main_count',
    'public_slots', 'main', 'secondary', 'pairings',
)


def build_comparison_body(
    group_id: str,
    revision: FrozenRevision,
    public_slots: tuple[int, ...],
    public_ids: tuple[str, ...],
    pairings: tuple[FeasiblePairing, ...],
) -> bytes:
    """Build the V2 body.

    Only public ids, the in-group anonymous group id and whole-pairing
    aggregate totals are disclosed. Hidden beat ids, sequences, readings,
    per-beat candidates and per-beat costs stay at the source station.
    """
    body = {
        'group_id': group_id,
        'run_id': revision.run_id,
        'revision_id': revision.revision_id,
        'main_count': len(revision.main),
        'public_slots': list(public_slots),
        'main': list(public_ids),
        'secondary': [sample.sample_id for sample in revision.secondary],
        'pairings': [
            {'positions': list(feasible.secondary_indices), 'total_cost': feasible.total_cost}
            for feasible in pairings
        ],
    }
    return json.dumps(body, separators=(',', ':'), sort_keys=True).encode('utf-8')
