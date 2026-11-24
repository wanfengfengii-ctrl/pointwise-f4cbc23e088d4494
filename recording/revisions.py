from dataclasses import dataclass

from recording.import_run import _validate_window
from recording.revision_store import RevisionStore
from recording.validate_track import Track, validate_track


@dataclass(frozen=True, slots=True)
class FrozenRevision:
    revision_id: int
    run_id: str
    corrects: int | None
    main: Track
    secondary: Track
    window: tuple[int, int]


def freeze_run(store: RevisionStore, revision_id: int) -> int:
    record = store.load_revision(revision_id)
    if record is None:
        raise LookupError(f'unknown revision {revision_id}')
    if not record.frozen:
        validate_track('main track', record.main)
        validate_track('secondary track', record.secondary)
        _validate_window(record.window)
        if record.corrects is not None:
            origin = store.load_revision(record.corrects)
            if origin is None or origin.run_id != record.run_id:
                raise ValueError('the correction source is unavailable')
        store.commit_freeze(revision_id)
    return revision_id


def get_frozen_revision(store: RevisionStore, revision_id: int) -> FrozenRevision:
    record = store.load_revision(revision_id)
    if record is None or not record.frozen:
        raise LookupError(f'no frozen revision {revision_id}')
    return FrozenRevision(
        record.revision_id, record.run_id, record.corrects,
        record.main, record.secondary, record.window,
    )
