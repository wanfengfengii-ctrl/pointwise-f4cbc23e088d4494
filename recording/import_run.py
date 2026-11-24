from collections.abc import Iterable

from recording.revision_store import RevisionStore
from recording.validate_track import validate_track


def import_run(
    store: RevisionStore,
    run_id: str,
    main: Iterable,
    secondary: Iterable,
    *,
    corrects: int | None = None,
    window: tuple[int, int] = (2, 2),
) -> int:
    """Append one complete draft and return its revision number."""
    if type(run_id) is not str or not run_id.strip():
        raise ValueError('a recording id is required')
    main_track = validate_track('main track', main)
    secondary_track = validate_track('secondary track', secondary)
    widths = _validate_window(window)
    if corrects is not None:
        origin = store.load_revision(corrects)
        if origin is None or origin.run_id != run_id:
            raise ValueError('the correction must reference a revision of this recording')
    return store.append_draft(run_id, main_track, secondary_track, widths, corrects)


def _validate_window(window: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(window, (tuple, list)) or len(window) != 2:
        raise ValueError('the sampling window requires two widths')
    left, right = window
    if any(type(width) is not int or width < 0 for width in (left, right)):
        raise ValueError('sampling window widths must be nonnegative integers')
    return left, right
