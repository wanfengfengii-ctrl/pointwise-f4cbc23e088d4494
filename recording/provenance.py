from dataclasses import dataclass

from recording.revisions import FrozenRevision


@dataclass(frozen=True, slots=True)
class RevisionProvenance:
    run_id: str
    revision_id: int
    corrects: int | None


def describe_revision(revision: FrozenRevision) -> RevisionProvenance:
    return RevisionProvenance(revision.run_id, revision.revision_id, revision.corrects)
