import json
import sqlite3
import unittest
from contextlib import closing, contextmanager
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory

from intake.receipts import ReceiptStore
from issue.register import initialize_issue_store, issue_packet
from recording.import_run import import_run
from recording.revision_store import RevisionStore
from recording.revisions import freeze_run
from review.report_store import ReportStore


SAMPLES = Path(__file__).resolve().parent.parent / 'samples'
JOINT = (('A', '2'), ('B', '4'))


def sample(name='windowed_run'):
    return json.loads((SAMPLES / f'{name}.json').read_text(encoding='utf-8'))


def corrected_secondary(data):
    return [row for row in data['secondary'] if row[0] != data['remove_secondary']]


def freeze_sample(store, data, *, corrects=None, secondary=None):
    if secondary is None:
        secondary = data['secondary']
    draft = import_run(store, data['run_id'], data['main'], secondary, corrects=corrects)
    return freeze_run(store, draft)


def brute_force(main, secondary, public, anchors=(), window=(2, 2)):
    """Independent oracle. List increasing index combinations and score raw samples."""
    fixed = dict(anchors)
    public_positions = [index for index, row in enumerate(main) if row[0] in public]
    left, right = window
    best = None
    for indices in combinations(range(len(secondary)), len(main)):
        total = 0
        for (primary, sequence, reading), index in zip(main, indices):
            secondary_id, time, value = secondary[index]
            if not sequence - left <= time <= sequence + right:
                break
            if primary in fixed and fixed[primary] != secondary_id:
                break
            total += abs(reading - value)
        else:
            projected = tuple(indices[index] for index in public_positions)
            score = total, projected
            if best is None or score < best:
                best = score
    if best is None:
        return None, None
    total, projected = best
    pairs = tuple((main[index][0], secondary[j][0]) for index, j in zip(public_positions, projected))
    return total, pairs


@contextmanager
def reject_commit(connection):
    refused = []

    def authorizer(action, operation, _argument, _database, _trigger):
        if action == sqlite3.SQLITE_TRANSACTION and operation == 'COMMIT':
            refused.append(operation)
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorizer)
    try:
        yield refused
    finally:
        connection.set_authorizer(None)


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source_path = self.root / 'station.sqlite'
        self.intake_path = self.root / 'night.sqlite'

    @contextmanager
    def source(self):
        with closing(sqlite3.connect(self.source_path)) as connection:
            store = RevisionStore(connection)
            store.initialize()
            initialize_issue_store(connection)
            yield store

    @contextmanager
    def night(self):
        with closing(sqlite3.connect(self.intake_path)) as connection:
            receipts, reports = ReceiptStore(connection), ReportStore(connection)
            receipts.initialize()
            reports.initialize()
            yield receipts, reports

    def issue_sample(self, data, *, disclosure=None):
        if disclosure is None:
            disclosure = data['public']
        with self.source() as store:
            revision = freeze_sample(store, data)
            return issue_packet(store, revision, disclosure)

    def issue_both_revisions(self):
        data = sample()
        with self.source() as store:
            original = freeze_sample(store, data)
            correction = freeze_sample(store, data, corrects=original, secondary=corrected_secondary(data))
            return (
                issue_packet(store, original, data['public']),
                issue_packet(store, correction, data['public']),
            )
