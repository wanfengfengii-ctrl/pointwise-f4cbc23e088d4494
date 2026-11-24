import json
import sqlite3
import uuid
from dataclasses import dataclass

from recording.revisions import FrozenRevision


MAX_PUBLIC_MAIN = 6
MAX_SECONDARY = 12


@dataclass(frozen=True, slots=True)
class ComparisonGroup:
    group_id: str
    run_id: str
    main: tuple[tuple[str, int], ...]
    secondary: tuple[tuple[str, int], ...]
    public_slots: tuple[int, ...]
    public_ids: tuple[str, ...]
    base_revision_id: int


class ComparisonGroupStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS comparison_groups (
                group_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                base_revision_id INTEGER NOT NULL,
                layout TEXT NOT NULL
            )
        ''')

    def open_group(self, group: ComparisonGroup) -> str:
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('group opening requires an idle connection')
        layout = {
            'main': list(group.main),
            'secondary': list(group.secondary),
            'public_slots': list(group.public_slots),
            'public_ids': list(group.public_ids),
        }
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            self.connection.execute('''
                INSERT INTO comparison_groups (group_id, run_id, base_revision_id, layout)
                VALUES (?, ?, ?, ?)
            ''', (group.group_id, group.run_id, group.base_revision_id,
                  json.dumps(layout, separators=(',', ':'), sort_keys=True)))
        return group.group_id

    def load_group(self, group_id: str) -> ComparisonGroup | None:
        if type(group_id) is not str or not group_id:
            raise ValueError('invalid group id')
        row = self.connection.execute('''
            SELECT run_id, base_revision_id, layout
            FROM comparison_groups WHERE group_id = ?
        ''', (group_id,)).fetchone()
        if row is None:
            return None
        run_id, base_revision_id, payload = row
        layout = json.loads(payload)
        return ComparisonGroup(
            group_id, run_id,
            tuple(tuple(item) for item in layout['main']),
            tuple(tuple(item) for item in layout['secondary']),
            tuple(layout['public_slots']),
            tuple(layout['public_ids']),
            base_revision_id,
        )


def new_group_id() -> str:
    return uuid.uuid4().hex


def build_group(group_id: str, revision: FrozenRevision, public_ids) -> ComparisonGroup:
    if type(group_id) is not str or not group_id:
        raise ValueError('invalid group id')
    main = tuple((sample.sample_id, sample.sequence) for sample in revision.main)
    secondary = tuple((sample.sample_id, sample.sequence) for sample in revision.secondary)
    if isinstance(public_ids, (str, bytes)):
        raise ValueError('public ids require a collection of main sample ids')
    try:
        supplied = iter(public_ids)
    except TypeError as error:
        raise ValueError('public ids require a collection of main sample ids') from error

    known = {sample.sample_id for sample in revision.main}
    selected = set()
    ordered = []
    for sample_id in supplied:
        if type(sample_id) is not str or sample_id not in known:
            raise ValueError(f'unknown public main sample {sample_id!r}')
        if sample_id in selected:
            raise ValueError(f'repeated public main sample {sample_id!r}')
        selected.add(sample_id)
        ordered.append(sample_id)
    if len(selected) > MAX_PUBLIC_MAIN:
        raise ValueError('a comparison group allows at most six public main samples')
    if len(secondary) > MAX_SECONDARY:
        raise ValueError('a comparison group allows at most twelve secondary samples')

    slots = tuple(index for index, sample in enumerate(revision.main) if sample.sample_id in selected)
    return ComparisonGroup(
        group_id, revision.run_id, main, secondary, slots, tuple(ordered),
        revision.revision_id,
    )
