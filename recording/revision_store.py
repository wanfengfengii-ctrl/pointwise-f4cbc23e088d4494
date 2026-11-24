import json
import sqlite3
from dataclasses import dataclass

from recording.validate_track import Sample, Track


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    revision_id: int
    run_id: str
    corrects: int | None
    main: Track
    secondary: Track
    window: tuple[int, int]
    frozen: bool


class RevisionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS recording_revisions (
                revision_id INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL,
                corrects INTEGER,
                main_track TEXT NOT NULL,
                secondary_track TEXT NOT NULL,
                window TEXT NOT NULL,
                frozen INTEGER NOT NULL DEFAULT 0 CHECK (frozen IN (0, 1))
            )
        ''')

    def append_draft(
        self, run_id: str, main: Track, secondary: Track,
        window: tuple[int, int], corrects: int | None,
    ) -> int:
        data = (run_id, corrects, _encode_track(main), _encode_track(secondary), json.dumps(window))
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('draft import requires an idle connection')
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            cursor = self.connection.execute('''
                INSERT INTO recording_revisions (run_id, corrects, main_track, secondary_track, window)
                VALUES (?, ?, ?, ?, ?)
            ''', data)
            revision_id = cursor.lastrowid
        return revision_id

    def load_revision(self, revision_id: int) -> RevisionRecord | None:
        _check_revision_id(revision_id)
        row = self.connection.execute('''
            SELECT run_id, corrects, main_track, secondary_track, window, frozen
            FROM recording_revisions WHERE revision_id = ?
        ''', (revision_id,)).fetchone()
        if row is None:
            return None
        run_id, corrects, main, secondary, window, frozen = row
        return RevisionRecord(
            revision_id, run_id, corrects, _decode_track(main), _decode_track(secondary),
            tuple(json.loads(window)), bool(frozen),
        )

    def commit_freeze(self, revision_id: int) -> None:
        _check_revision_id(revision_id)
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('freeze requires an idle connection')
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            updated = self.connection.execute('''
                UPDATE recording_revisions SET frozen = 1
                WHERE revision_id = ? AND frozen = 0
            ''', (revision_id,))
            if not updated.rowcount:
                found = self.connection.execute('''
                    SELECT 1 FROM recording_revisions WHERE revision_id = ?
                ''', (revision_id,)).fetchone()
                if found is None:
                    raise LookupError(f'unknown revision {revision_id}')


def _check_revision_id(revision_id: int) -> None:
    if type(revision_id) is not int or not 0 < revision_id < 2**63:
        raise ValueError('invalid revision id')


def _encode_track(track: Track) -> str:
    return json.dumps([(sample.sample_id, sample.sequence, sample.reading) for sample in track])


def _decode_track(data: str) -> Track:
    return tuple(Sample(*row) for row in json.loads(data))
