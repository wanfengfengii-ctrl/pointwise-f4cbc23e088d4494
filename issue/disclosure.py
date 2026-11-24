from collections.abc import Iterable
from dataclasses import dataclass

from recording.revisions import FrozenRevision


@dataclass(frozen=True, slots=True)
class Disclosure:
    main_indices: tuple[int, ...]
    main_ids: tuple[str, ...]
    secondary_ids: tuple[str, ...]


def resolve_disclosure(revision: FrozenRevision, public_ids: Iterable[str]) -> Disclosure:
    known = {sample.sample_id for sample in revision.main}
    if isinstance(public_ids, (str, bytes)):
        raise ValueError('disclosure requires a collection of main sample ids')
    try:
        supplied = iter(public_ids)
    except TypeError as error:
        raise ValueError('disclosure requires a collection of main sample ids') from error
    selected = set()
    for sample_id in supplied:
        if type(sample_id) is not str or sample_id not in known:
            raise ValueError(f'unknown main sample {sample_id!r}')
        if sample_id in selected:
            raise ValueError(f'repeated disclosure sample {sample_id!r}')
        selected.add(sample_id)
    indices = tuple(index for index, sample in enumerate(revision.main) if sample.sample_id in selected)
    return Disclosure(
        indices,
        tuple(revision.main[index].sample_id for index in indices),
        tuple(sample.sample_id for sample in revision.secondary),
    )
