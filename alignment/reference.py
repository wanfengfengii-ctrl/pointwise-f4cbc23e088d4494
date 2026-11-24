from collections.abc import Iterable

from alignment.candidates import build_candidates
from alignment.costs import price_candidates
from alignment.solver import solve_alignment
from alignment.witness import AlignmentWitness, build_witness
from recording.revision_store import RevisionStore
from recording.revisions import FrozenRevision, get_frozen_revision


def normalize_reference_anchors(
    revision: FrozenRevision, anchors: Iterable[tuple[str, str]],
) -> dict[int, int]:
    main = {sample.sample_id: index for index, sample in enumerate(revision.main)}
    secondary = {sample.sample_id: index for index, sample in enumerate(revision.secondary)}
    try:
        items = iter(anchors)
    except TypeError as error:
        raise ValueError('anchors must be a sequence of pairs') from error
    result = {}
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError('each anchor requires two sample ids')
        primary_id, secondary_id = item
        if type(primary_id) is not str or primary_id not in main:
            raise ValueError(f'unknown main sample {primary_id!r}')
        if type(secondary_id) is not str or secondary_id not in secondary:
            raise ValueError(f'unknown secondary sample {secondary_id!r}')
        index = main[primary_id]
        if index in result:
            raise ValueError(f'repeated main sample {primary_id!r}')
        result[index] = secondary[secondary_id]
    return result


def preview(
    store: RevisionStore, revision_id: int, anchors: Iterable[tuple[str, str]] = (),
) -> AlignmentWitness | None:
    revision = get_frozen_revision(store, revision_id)
    fixed = normalize_reference_anchors(revision, anchors)
    layers = price_candidates(revision, build_candidates(revision))
    solution = solve_alignment(layers, fixed)
    if solution is None:
        return None
    return build_witness(revision, layers, solution)
