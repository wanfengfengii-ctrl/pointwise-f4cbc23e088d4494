import sqlite3
from dataclasses import dataclass

from intake.verify_envelope import VerifiedEnvelope, verify_envelope
from intake.verify_evidence import VerifiedEvidence, verify_evidence
from issue.envelope import IssueRegistration


@dataclass(frozen=True, slots=True)
class Receipt:
    receipt_id: int
    registration: IssueRegistration
    wire: bytes
    evidence: VerifiedEvidence


class ReceiptStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS intake_receipts (
                receipt_id INTEGER PRIMARY KEY,
                issue_id INTEGER NOT NULL,
                run_id TEXT NOT NULL,
                revision_id INTEGER NOT NULL,
                body_sha256 TEXT NOT NULL,
                wire BLOB NOT NULL
            )
        ''')

    def record_receipt(self, envelope: VerifiedEnvelope) -> int:
        registration = envelope.registration
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('packet receipt requires an idle connection')
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            cursor = self.connection.execute('''
                INSERT INTO intake_receipts (issue_id, run_id, revision_id, body_sha256, wire)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                registration.issue_id, registration.run_id, registration.revision_id,
                registration.body_sha256, envelope.wire,
            ))
            receipt_id = cursor.lastrowid
        return receipt_id

    def get_receipt(self, receipt_id: int) -> Receipt | None:
        if type(receipt_id) is not int or not 0 < receipt_id < 2**63:
            raise ValueError('invalid receipt id')
        row = self.connection.execute('''
            SELECT issue_id, run_id, revision_id, body_sha256, wire
            FROM intake_receipts WHERE receipt_id = ?
        ''', (receipt_id,)).fetchone()
        if row is None:
            return None
        issue_id, run_id, revision_id, digest, wire = row
        registration = IssueRegistration(issue_id, run_id, revision_id, digest)
        verified = verify_envelope(wire, registration)
        return Receipt(receipt_id, registration, wire, verify_evidence(verified))
