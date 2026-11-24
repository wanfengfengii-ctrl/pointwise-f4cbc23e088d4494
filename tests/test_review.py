import sqlite3
from itertools import product

from intake.receive import receive_packet
from review.publish import sign_review
from review.retrieve import get_report
from tests.support import ArchiveCase, JOINT, brute_force, corrected_secondary, reject_commit, sample


class ReviewTests(ArchiveCase):
    def test_offline_joint_queries_match_independent_full_recording_oracle(self):
        data = sample()
        original, correction = self.issue_both_revisions()
        with self.night() as (receipts, reports):
            for packet, secondary in ((original, data['secondary']), (correction, corrected_secondary(data))):
                receipt_id = receive_packet(receipts, *packet)
                query_set = [()]
                ids = [row[0] for row in secondary]
                query_set.extend(((main_id, value),) for main_id, value in product(data['public'], ids))
                query_set.extend((('B', b), ('A', a)) for a, b in product(ids, repeat=2))
                for anchors in query_set:
                    with self.subTest(revision=packet[1].revision_id, anchors=anchors):
                        expected = brute_force(data['main'], secondary, data['public'], anchors)
                        actual = sign_review(receipts, reports, receipt_id, anchors)
                        self.assertEqual((actual.total_cost, actual.pairs), expected)
                        self.assertEqual(actual.anchors, tuple(sorted(anchors)))
                        self.assertEqual(actual.receipt_id, receipt_id)
                self.assertEqual(sign_review(receipts, reports, receipt_id, JOINT[:1]).total_cost, 0)
                self.assertEqual(sign_review(receipts, reports, receipt_id, JOINT[1:]).total_cost, 0)
                result = sign_review(receipts, reports, receipt_id, JOINT)
                expected = (5, JOINT) if packet == original else (None, None)
                self.assertEqual((result.total_cost, result.pairs), expected)

    def test_old_receipt_and_signed_result_survive_reissue_and_restart(self):
        original, correction = self.issue_both_revisions()
        with self.night() as (receipts, reports):
            old_id = receive_packet(receipts, *original)
            old_report = sign_review(receipts, reports, old_id, JOINT)
        with self.night() as (receipts, reports):
            new_id = receive_packet(receipts, *correction)
            new_report = sign_review(receipts, reports, new_id, JOINT)
            self.assertNotEqual(new_id, old_id)
            self.assertIsNone(new_report.total_cost)
            self.assertIsNone(new_report.pairs)
        with self.night() as (receipts, reports):
            self.assertEqual(get_report(reports, old_report.report_id), old_report)
            self.assertEqual(get_report(reports, new_report.report_id), new_report)
            self.assertEqual((old_report.total_cost, old_report.pairs, old_report.receipt_id), (5, JOINT, old_id))
            self.assertEqual(old_report.body_sha256, original[1].body_sha256)
            self.assertEqual(receipts.get_receipt(old_id).registration, original[1])
            self.assertIsNone(get_report(reports, new_report.report_id + 1))

    def test_invalid_anchors_leave_no_report(self):
        packet = self.issue_sample(sample())
        with self.night() as (receipts, reports):
            receipt_id = receive_packet(receipts, *packet)
            before = sign_review(receipts, reports, receipt_id)
            invalid = (
                (('H', '3'),), (('Z', '2'),), (('A', 'A'),),
                (('A', '1'), ('A', '2')), (('A', '1'), ('B', '4'), ('A', '2')),
                (('A',),),
            )
            for anchors in invalid:
                with self.subTest(anchors=anchors), self.assertRaises(ValueError):
                    sign_review(receipts, reports, receipt_id, anchors)
            with self.assertRaises(LookupError):
                sign_review(receipts, reports, receipt_id + 1)
            self.assertEqual(reports.connection.execute('SELECT count(*) FROM signed_reports').fetchone()[0], 1)
            self.assertEqual(get_report(reports, before.report_id), before)
            conflict = sign_review(receipts, reports, receipt_id, [('A', '4'), ('B', '4')])
            self.assertEqual((conflict.total_cost, conflict.pairs), (None, None))

    def test_public_tie_order_counts_hidden_prefix_and_suffix(self):
        data = sample('tied_run')
        packet = self.issue_sample(data)
        with self.night() as (receipts, reports):
            receipt_id = receive_packet(receipts, *packet)
            signed = sign_review(receipts, reports, receipt_id)
            later = sign_review(receipts, reports, receipt_id, [('A', 'S10')])
            self.assertEqual((signed.total_cost, signed.pairs), (5, (('A', 'S2'), ('B', 'S11'))))
            self.assertEqual((later.total_cost, later.pairs), (5, (('A', 'S10'), ('B', 'S11'))))
            self.assertEqual((signed.total_cost, signed.pairs),
                             brute_force(data['main'], data['secondary'], data['public']))
        with self.night() as (_, reports):
            self.assertEqual(get_report(reports, signed.report_id), signed)

    def test_empty_disclosure_still_scores_entire_recording(self):
        packet = self.issue_sample(sample('tied_run'), disclosure=())
        with self.night() as (receipts, reports):
            receipt_id = receive_packet(receipts, *packet)
            signed = sign_review(receipts, reports, receipt_id)
            self.assertEqual((signed.total_cost, signed.pairs), (5, ()))
            with self.assertRaises(ValueError):
                sign_review(receipts, reports, receipt_id, [('A', 'S2')])

    def test_empty_path_and_impossible_recordings_have_distinct_results(self):
        no_main = {'run_id': 'EMPTY', 'main': [], 'secondary': [], 'public': []}
        no_candidate = {'run_id': 'UNMATCHABLE', 'main': [['A', 0, 0]], 'secondary': [], 'public': []}
        packets = [self.issue_sample(data) for data in (no_main, no_candidate)]
        with self.night() as (receipts, reports):
            results = []
            for packet in packets:
                receipt_id = receive_packet(receipts, *packet)
                report = sign_review(receipts, reports, receipt_id)
                results.append((report.total_cost, report.pairs))
            self.assertEqual(results, [(0, ()), (None, None)])

    def test_commit_refusal_leaves_no_new_report_after_restart(self):
        packet = self.issue_sample(sample())
        with self.night() as (receipts, reports):
            receipt_id = receive_packet(receipts, *packet)
            before = sign_review(receipts, reports, receipt_id, JOINT)
            changes = reports.connection.total_changes
            with reject_commit(reports.connection) as refused:
                with self.assertRaises(sqlite3.DatabaseError):
                    sign_review(receipts, reports, receipt_id, JOINT[:1])
            self.assertEqual(refused, ['COMMIT'])
            self.assertEqual(reports.connection.total_changes, changes + 1)
            self.assertFalse(reports.connection.in_transaction)
        with self.night() as (receipts, reports):
            self.assertEqual(reports.connection.execute('SELECT count(*) FROM signed_reports').fetchone()[0], 1)
            self.assertIsNone(get_report(reports, before.report_id + 1))
            self.assertEqual(get_report(reports, before.report_id), before)
            self.assertEqual(receipts.get_receipt(receipt_id).registration.body_sha256, before.body_sha256)
            resumed = sign_review(receipts, reports, receipt_id, JOINT[:1])
            self.assertEqual(resumed.total_cost, 0)

    def test_damaged_receipt_cannot_create_another_report(self):
        packet = self.issue_sample(sample())
        with self.night() as (receipts, reports):
            receipt_id = receive_packet(receipts, *packet)
            old = sign_review(receipts, reports, receipt_id)
            with receipts.connection:
                receipts.connection.execute('UPDATE intake_receipts SET wire = ? WHERE receipt_id = ?',
                                            (b'{}', receipt_id))
            with self.assertRaises(ValueError):
                sign_review(receipts, reports, receipt_id)
            self.assertIsNone(get_report(reports, old.report_id + 1))
            self.assertEqual(get_report(reports, old.report_id), old)
