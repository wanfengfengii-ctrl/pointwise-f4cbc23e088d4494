import json
import sqlite3
from dataclasses import dataclass


Pairs = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SignedReport:
    report_id: int
    receipt_id: int
    issue_id: int
    run_id: str
    revision_id: int
    body_sha256: str
    anchors: Pairs
    total_cost: int | None
    pairs: Pairs | None


@dataclass(frozen=True, slots=True)
class SharedSetupSourceRecord:
    receipt_id: int
    issue_id: int
    revision_id: int
    body_sha256: str


@dataclass(frozen=True, slots=True)
class SharedSetupReport:
    report_id: int
    group_id: str
    run_id: str
    sources: tuple[SharedSetupSourceRecord, ...]
    upper_cost: int | None
    pairs: Pairs | None


class ReportStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS signed_reports (
                report_id INTEGER PRIMARY KEY,
                receipt_id INTEGER NOT NULL,
                snapshot TEXT NOT NULL
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS shared_setup_reports (
                report_id INTEGER PRIMARY KEY,
                snapshot TEXT NOT NULL
            )
        ''')

    def commit_report(
        self, *, receipt_id: int, issue_id: int, run_id: str, revision_id: int,
        body_sha256: str, anchors: Pairs, total_cost: int | None, pairs: Pairs | None,
    ) -> SignedReport:
        if (total_cost is None) != (pairs is None):
            raise ValueError('the report cost and pairings must describe the same result')
        snapshot = {
            'issue_id': issue_id,
            'run_id': run_id,
            'revision_id': revision_id,
            'body_sha256': body_sha256,
            'anchors': anchors,
            'total_cost': total_cost,
            'pairs': pairs,
        }
        payload = json.dumps(snapshot, separators=(',', ':'), sort_keys=True)
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('report signing requires an idle connection')
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            cursor = self.connection.execute('''
                INSERT INTO signed_reports (receipt_id, snapshot) VALUES (?, ?)
            ''', (receipt_id, payload))
            report_id = cursor.lastrowid
        return SignedReport(report_id, receipt_id, issue_id, run_id, revision_id, body_sha256, anchors, total_cost, pairs)

    def load_report(self, report_id: int) -> SignedReport | None:
        if type(report_id) is not int or not 0 < report_id < 2**63:
            raise ValueError('invalid report id')
        row = self.connection.execute('''
            SELECT receipt_id, snapshot FROM signed_reports WHERE report_id = ?
        ''', (report_id,)).fetchone()
        if row is None:
            return None
        receipt_id, payload = row
        data = json.loads(payload)
        anchors = tuple(tuple(pair) for pair in data['anchors'])
        pairs = None if data['pairs'] is None else tuple(tuple(pair) for pair in data['pairs'])
        return SignedReport(
            report_id, receipt_id, data['issue_id'], data['run_id'], data['revision_id'],
            data['body_sha256'], anchors, data['total_cost'], pairs,
        )

    def commit_shared_setup_report(
        self, *, group_id: str, run_id: str,
        sources: tuple[SharedSetupSourceRecord, ...],
        upper_cost: int | None, pairs: Pairs | None,
    ) -> SharedSetupReport:
        if (upper_cost is None) != (pairs is None):
            raise ValueError('the report cost and pairings must describe the same result')
        snapshot = {
            'group_id': group_id,
            'run_id': run_id,
            'sources': [
                {
                    'receipt_id': source.receipt_id,
                    'issue_id': source.issue_id,
                    'revision_id': source.revision_id,
                    'body_sha256': source.body_sha256,
                }
                for source in sources
            ],
            'upper_cost': upper_cost,
            'pairs': pairs,
        }
        payload = json.dumps(snapshot, separators=(',', ':'), sort_keys=True)
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('report signing requires an idle connection')
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            cursor = self.connection.execute('''
                INSERT INTO shared_setup_reports (snapshot) VALUES (?)
            ''', (payload,))
            report_id = cursor.lastrowid
        return SharedSetupReport(report_id, group_id, run_id, sources, upper_cost, pairs)

    def load_shared_setup_report(self, report_id: int) -> SharedSetupReport | None:
        if type(report_id) is not int or not 0 < report_id < 2**63:
            raise ValueError('invalid report id')
        row = self.connection.execute('''
            SELECT snapshot FROM shared_setup_reports WHERE report_id = ?
        ''', (report_id,)).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        sources = tuple(
            SharedSetupSourceRecord(
                item['receipt_id'], item['issue_id'], item['revision_id'], item['body_sha256'],
            )
            for item in data['sources']
        )
        pairs = None if data['pairs'] is None else tuple(tuple(pair) for pair in data['pairs'])
        return SharedSetupReport(
            report_id, data['group_id'], data['run_id'], sources,
            data['upper_cost'], pairs,
        )
