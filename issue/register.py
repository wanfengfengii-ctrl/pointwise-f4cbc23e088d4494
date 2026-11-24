import sqlite3
from collections.abc import Iterable

from alignment.candidates import build_candidates
from alignment.costs import price_candidates
from issue.body import build_body
from issue.disclosure import resolve_disclosure
from issue.envelope import IssueRegistration, body_digest, seal_envelope
from issue.evidence import build_evidence
from recording.provenance import describe_revision
from recording.revision_store import RevisionStore
from recording.revisions import get_frozen_revision


def initialize_issue_store(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS issued_packets (
            issue_id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            revision_id INTEGER NOT NULL,
            body_sha256 TEXT NOT NULL,
            body BLOB NOT NULL
        )
    ''')


def issue_packet(
    store: RevisionStore, revision_id: int, public_ids: Iterable[str],
) -> tuple[bytes, IssueRegistration]:
    revision = get_frozen_revision(store, revision_id)
    origin = describe_revision(revision)
    disclosure = resolve_disclosure(revision, public_ids)
    layers = price_candidates(revision, build_candidates(revision))
    evidence = build_evidence(layers, disclosure)
    body = build_body(origin, disclosure, evidence)
    digest = body_digest(body)

    connection = store.connection
    if connection.in_transaction:
        raise sqlite3.ProgrammingError('packet issue requires an idle connection')
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        cursor = connection.execute('''
            INSERT INTO issued_packets (run_id, revision_id, body_sha256, body)
            VALUES (?, ?, ?, ?)
        ''', (origin.run_id, origin.revision_id, digest, body))
        registration = IssueRegistration(cursor.lastrowid, origin.run_id, origin.revision_id, digest)
        packet = seal_envelope(registration.issue_id, body)
    return packet, registration


def get_issue_registration(connection: sqlite3.Connection, issue_id: int) -> IssueRegistration | None:
    if type(issue_id) is not int or not 0 < issue_id < 2**63:
        raise ValueError('invalid issue id')
    row = connection.execute('''
        SELECT run_id, revision_id, body_sha256 FROM issued_packets WHERE issue_id = ?
    ''', (issue_id,)).fetchone()
    return None if row is None else IssueRegistration(issue_id, *row)
