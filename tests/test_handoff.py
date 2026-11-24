import json
import sqlite3
from dataclasses import replace

from intake.receive import receive_packet
from issue.envelope import body_digest, read_envelope, seal_envelope
from issue.register import get_issue_registration, issue_packet
from review.publish import sign_review
from tests.support import ArchiveCase, JOINT, freeze_sample, reject_commit, sample


class HandoffTests(ArchiveCase):
    def test_disclosure_bytes_survive_source_shutdown(self):
        data = sample()
        with self.source() as store:
            revision = freeze_sample(store, data)
            wire, registration = issue_packet(store, revision, ['B', 'A'])
            original_registration = get_issue_registration(store.connection, registration.issue_id)
            self.assertEqual(registration, original_registration)
            recorded_body = store.connection.execute(
                'SELECT body FROM issued_packets WHERE issue_id = ?', (registration.issue_id,),
            ).fetchone()[0]
        self.source_path.rename(self.root / 'station-offline.sqlite')
        self.assertFalse(self.source_path.exists())

        body_bytes = read_envelope(wire).body
        self.assertEqual(body_bytes, recorded_body)
        body = json.loads(body_bytes)
        self.assertEqual(body.keys(), {'run_id', 'revision_id', 'main', 'secondary', 'evidence'})
        self.assertEqual(body['main'], ['A', 'B'])
        self.assertEqual(body['secondary'], ['1', '2', '3', '4', '5'])
        self.assertEqual(body['revision_id'], revision)
        self.assertNotIn(b'"H"', body_bytes)
        self.assertNotIn(b'"reading"', body_bytes)
        self.assertNotIn(b'"candidates"', body_bytes)
        with self.night() as (receipts, reports):
            receipt_id = receive_packet(receipts, wire, original_registration)
            self.assertEqual(receipts.get_receipt(receipt_id).wire, wire)
            report = sign_review(receipts, reports, receipt_id, JOINT)
            self.assertEqual((report.total_cost, report.pairs), (5, JOINT))

    def test_offline_evidence_distinguishes_the_two_revisions(self):
        original, correction = self.issue_both_revisions()
        with self.night() as (receipts, reports):
            results = []
            for packet in (original, correction):
                receipt_id = receive_packet(receipts, *packet)
                result = sign_review(receipts, reports, receipt_id, JOINT)
                results.append((result.total_cost, result.pairs))
            self.assertEqual(results, [(5, JOINT), (None, None)])

    def test_mixed_registrations_and_changed_bytes_leave_no_receipt(self):
        original, correction = self.issue_both_revisions()
        with self.night() as (receipts, _):
            old_id = receive_packet(receipts, *original)
            for wire, registration in ((original[0], correction[1]), (correction[0], original[1])):
                with self.assertRaises(ValueError):
                    receive_packet(receipts, wire, registration)
            changed_body = read_envelope(original[0]).body + b' '
            edited_packet = seal_envelope(original[1].issue_id, changed_body)
            with self.assertRaises(ValueError):
                receive_packet(receipts, edited_packet, original[1])
        with self.night() as (receipts, _):
            self.assertEqual(receipts.connection.execute('SELECT count(*) FROM intake_receipts').fetchone()[0], 1)
            self.assertEqual(receipts.get_receipt(old_id).registration, original[1])
            self.assertIsNone(receipts.get_receipt(old_id + 1))

    def test_registered_bytes_still_require_valid_body_structure(self):
        wire, registration = self.issue_sample(sample())
        body = json.loads(read_envelope(wire).body)
        body['secondary'].append(body['secondary'][0])
        invalid = json.dumps(body).encode('utf-8')
        bad_registration = replace(registration, body_sha256=body_digest(invalid))
        with self.night() as (receipts, _):
            with self.assertRaisesRegex(ValueError, 'duplicate ids'):
                receive_packet(receipts, seal_envelope(registration.issue_id, invalid), bad_registration)
            self.assertEqual(receipts.connection.execute('SELECT count(*) FROM intake_receipts').fetchone()[0], 0)

    def test_issue_and_receipt_commit_refusals_leave_no_new_rows(self):
        data = sample()
        with self.source() as store:
            revision = freeze_sample(store, data)
            with self.assertRaises(ValueError):
                issue_packet(store, revision, ['A', 'A'])
            with reject_commit(store.connection) as refused:
                with self.assertRaises(sqlite3.DatabaseError):
                    issue_packet(store, revision, data['public'])
            self.assertEqual(refused, ['COMMIT'])
            self.assertEqual(store.connection.execute('SELECT count(*) FROM issued_packets').fetchone()[0], 0)
            packet = issue_packet(store, revision, data['public'])
        with self.night() as (receipts, _):
            with reject_commit(receipts.connection) as refused:
                with self.assertRaises(sqlite3.DatabaseError):
                    receive_packet(receipts, *packet)
            self.assertEqual(refused, ['COMMIT'])
        with self.night() as (receipts, _):
            self.assertEqual(receipts.connection.execute('SELECT count(*) FROM intake_receipts').fetchone()[0], 0)
            receipt_id = receive_packet(receipts, *packet)
            self.assertEqual(receipts.get_receipt(receipt_id).registration, packet[1])
