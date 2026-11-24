import json
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from intake.receipts import ReceiptStore
from intake.receive import receive_packet
from issue.envelope import V2, body_digest, read_envelope, seal_envelope
from issue.register import (
    get_issue_registration,
    initialize_issue_store,
    issue_comparison_packet,
    issue_packet,
    open_comparison_group,
)
from recording.import_run import import_run
from recording.revision_store import RevisionStore
from recording.revisions import freeze_run
from review.publish import sign_review, sign_shared_setup
from review.report_store import ReportStore
from review.retrieve import get_report, get_shared_setup_report
from tests.support import reject_commit


FIXTURE = Path(__file__).resolve().parents[1] / 'samples' / 'setup_comparison.json'
TIED = Path(__file__).resolve().parents[1] / 'samples' / 'tied_run.json'


def import_comparison_case(store, case):
    parent = None
    revisions = {}
    for variant in case['revisions']:
        main = [(sample_id, sequence, variant['readings'].get(sample_id, value))
                for sample_id, sequence, value in case['main']]
        draft = import_run(store, case['run_id'], main, case['secondary'],
                           corrects=parent, window=variant['window'])
        parent = freeze_run(store, draft)
        revisions[variant['name']] = parent
    return revisions


def seal_mutated(registration, body):
    payload = json.dumps(body, separators=(',', ':'), sort_keys=True).encode()
    return (
        seal_envelope(registration.issue_id, payload, V2),
        replace(registration, body_sha256=body_digest(payload)),
    )


class SharedSetupFixtureTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source_path = self.root / 'station.sqlite'
        self.night_path = self.root / 'night.sqlite'
        self.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.tied = json.loads(TIED.read_text(encoding='utf-8'))
        self.packets = {}
        self.revisions = {}
        self.groups = {}
        with closing(sqlite3.connect(self.source_path)) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            for case_name in ('single', 'double'):
                case = self.fixture[case_name]
                revisions = import_comparison_case(store, case)
                base = revisions[case['revisions'][0]['name']]
                group_id = open_comparison_group(store, base, case['public'])
                self.groups[case_name] = group_id
                self.revisions[case_name] = revisions
                for name, revision_id in revisions.items():
                    self.packets[(case_name, name)] = issue_comparison_packet(
                        store, group_id, revision_id)
            first = freeze_run(store, import_run(
                store, self.tied['run_id'], self.tied['main'], self.tied['secondary']))
            second = freeze_run(store, import_run(
                store, self.tied['run_id'], self.tied['main'], self.tied['secondary'],
                corrects=first))
            tied_group = open_comparison_group(store, first, self.tied['public'])
            empty_group = open_comparison_group(store, first, ())
            self.tied_revisions = (first, second)
            self.groups['tied'] = tied_group
            self.groups['tied_empty'] = empty_group
            self.packets[('tied', 'a')] = issue_comparison_packet(store, tied_group, first)
            self.packets[('tied', 'b')] = issue_comparison_packet(store, tied_group, second)
            self.packets[('tied_empty', 'a')] = issue_comparison_packet(store, empty_group, first)
            self.packets[('tied_empty', 'b')] = issue_comparison_packet(store, empty_group, second)
            self.v1_packet = issue_packet(store, first, self.tied['public'])

    def _night(self):
        connection = sqlite3.connect(self.night_path)
        self.addCleanup(connection.close)
        receipts, reports = ReceiptStore(connection), ReportStore(connection)
        receipts.initialize()
        reports.initialize()
        return connection, receipts, reports

    def _receive_all(self, receipts):
        received = {
            key: receive_packet(receipts, wire, registration)
            for key, (wire, registration) in self.packets.items()
        }
        received[('v1',)] = receive_packet(receipts, *self.v1_packet)
        return received

    def _sign(self, receipts, reports, received, first_key, second_key):
        report = sign_shared_setup(
            receipts, reports, received[first_key], received[second_key])
        self.assertEqual(get_shared_setup_report(reports, report.report_id), report)
        return report

    def test_single_run_combination_costs_and_public_pairs(self):
        _, receipts, reports = self._night()
        received = self._receive_all(receipts)
        cases = [
            (('single', 'first'), ('single', 'second'), 4, (('A', 'U'), ('B', 'V'))),
            (('single', 'first'), ('single', 'third'), 0, (('A', 'U'), ('B', 'V'))),
            (('single', 'left'), ('single', 'right'), None, None),
            (('single', 'first'), ('single', 'right'), 4, (('A', 'U'), ('B', 'V'))),
        ]
        for first_key, second_key, cost, pairs in cases:
            with self.subTest(case=(first_key, second_key)):
                report = self._sign(receipts, reports, received, first_key, second_key)
                self.assertEqual((report.upper_cost, report.pairs), (cost, pairs))
                self.assertEqual(report.group_id, self.groups['single'])
                self.assertEqual(report.run_id, self.fixture['single']['run_id'])
                self.assertEqual(
                    [source.receipt_id for source in report.sources],
                    [received[first_key], received[second_key]])
                for source, key in zip(report.sources, (first_key, second_key)):
                    registration = self.packets[key][1]
                    self.assertEqual(source.issue_id, registration.issue_id)
                    self.assertEqual(source.revision_id, registration.revision_id)
                    self.assertEqual(source.body_sha256, registration.body_sha256)

    def test_double_run_hidden_beats_count_in_each_revision(self):
        _, receipts, reports = self._night()
        received = self._receive_all(receipts)
        report = self._sign(
            receipts, reports, received, ('double', 'first'), ('double', 'second'))
        self.assertEqual((report.upper_cost, report.pairs),
                         (4, (('A', 'U'), ('M', 'T'), ('B', 'V'))))
        # hidden beats still occupy positions in every disclosed pairing
        for wire, _ in (self.packets[('double', 'first')], self.packets[('double', 'second')]):
            body = json.loads(read_envelope(wire).body)
            self.assertTrue(all(len(row['positions']) == body['main_count'] for row in body['pairings']))

    def test_tied_run_uses_secondary_original_order_on_equal_costs(self):
        _, receipts, reports = self._night()
        received = self._receive_all(receipts)
        tied = self._sign(receipts, reports, received, ('tied', 'a'), ('tied', 'b'))
        self.assertEqual((tied.upper_cost, tied.pairs),
                         (5, (('A', 'S2'), ('B', 'S11'))))
        empty = self._sign(receipts, reports, received, ('tied_empty', 'a'), ('tied_empty', 'b'))
        self.assertEqual((empty.upper_cost, empty.pairs), (5, ()))
        self.assertNotEqual(tied.group_id, empty.group_id)

    def test_v2_bodies_keep_hidden_beat_details_at_the_station(self):
        for case_name in ('single', 'double'):
            for key, (wire, registration) in self.packets.items():
                if key[0] != case_name:
                    continue
                envelope = read_envelope(wire)
                self.assertEqual(envelope.version, V2)
                self.assertEqual(envelope.body_sha256, registration.body_sha256)
                text = envelope.body.decode('utf-8')
                self.assertNotIn('reading', text)
                self.assertNotIn('sequence', text)
                self.assertNotIn('candidate', text)
                body = json.loads(text)
                hidden = {sample[0] for sample in self.fixture[case_name]['main']} - set(
                    self.fixture[case_name]['public'])
                for sample_id in hidden:
                    self.assertNotIn(f'"{sample_id}"', text)
                self.assertEqual(body['group_id'], self.groups[case_name])
                self.assertTrue(all(
                    set(row) == {'positions', 'total_cost'} for row in body['pairings']))

    def test_changed_bytes_and_bad_bodies_are_rejected_without_a_receipt(self):
        connection, receipts, _ = self._night()
        wire, registration = self.packets[('single', 'first')]
        other_registration = self.packets[('single', 'second')][1]
        with self.assertRaises(ValueError):
            receive_packet(receipts, wire, other_registration)
        original = json.loads(read_envelope(wire).body)

        damaged = []
        body = json.loads(json.dumps(original))
        body['secondary'].append(body['secondary'][0])
        damaged.append(seal_mutated(registration, body))
        body = json.loads(json.dumps(original))
        body['pairings'].append(dict(body['pairings'][0]))
        damaged.append(seal_mutated(registration, body))
        body = json.loads(json.dumps(original))
        body['pairings'][0]['positions'].append(0)
        damaged.append(seal_mutated(registration, body))
        body = json.loads(json.dumps(original))
        body['unknown_field'] = 1
        damaged.append(seal_mutated(registration, body))
        body = json.loads(json.dumps(original))
        body['pairings'][0]['total_cost'] = -1
        damaged.append(seal_mutated(registration, body))
        for bad_wire, bad_registration in damaged:
            with self.subTest(body=bad_wire):
                with self.assertRaises(ValueError):
                    receive_packet(receipts, bad_wire, bad_registration)
        self.assertEqual(
            connection.execute('SELECT count(*) FROM intake_receipts').fetchone()[0], 0)

    def test_mixed_group_same_revision_and_v1_selections_are_refused(self):
        _, receipts, reports = self._night()
        received = self._receive_all(receipts)
        refusals = [
            (received[('single', 'first')], received[('v1',)]),
            (received[('v1',)], received[('single', 'first')]),
            (received[('single', 'first')], received[('double', 'first')]),
            (received[('tied', 'a')], received[('tied', 'a')]),
        ]
        for first_id, second_id in refusals:
            with self.subTest(selection=(first_id, second_id)):
                with self.assertRaises(ValueError):
                    sign_shared_setup(receipts, reports, first_id, second_id)
        with self.assertRaises(LookupError):
            sign_shared_setup(receipts, reports, 999, received[('tied', 'b')])
        # a V2 receipt cannot drive the V1 single-packet report
        with self.assertRaises(ValueError):
            sign_review(receipts, reports, received[('single', 'first')])
        # the V1 receipt still follows the original single-packet flow
        report = sign_review(receipts, reports, received[('v1',)])
        self.assertEqual((report.total_cost, report.pairs),
                         (5, (('A', 'S2'), ('B', 'S11'))))
        self.assertEqual(get_report(reports, report.report_id), report)

    def test_commit_refusal_creates_no_shared_report_and_reopen_keeps_values(self):
        connection, receipts, reports = self._night()
        received = self._receive_all(receipts)
        with reject_commit(connection) as refused:
            with self.assertRaises(sqlite3.DatabaseError):
                sign_shared_setup(
                    receipts, reports, received[('single', 'first')],
                    received[('single', 'second')])
        self.assertEqual(refused, ['COMMIT'])
        self.assertFalse(connection.in_transaction)
        self.assertEqual(
            connection.execute('SELECT count(*) FROM shared_setup_reports').fetchone()[0], 0)
        report = sign_shared_setup(
            receipts, reports, received[('single', 'first')],
            received[('single', 'second')])
        connection.close()

        with closing(sqlite3.connect(self.night_path)) as reopened:
            reports = ReportStore(reopened)
            reports.initialize()
            self.assertEqual(get_shared_setup_report(reports, report.report_id), report)
            self.assertIsNone(get_shared_setup_report(reports, report.report_id + 100))

    def test_group_qualification_and_layout_mismatches_are_value_errors(self):
        with closing(sqlite3.connect(self.source_path)) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            revision_id = self.revisions['single']['first']
            with self.assertRaises(ValueError):
                open_comparison_group(store, revision_id, ['A', 'A'])
            with self.assertRaises(ValueError):
                open_comparison_group(store, revision_id, ['UNKNOWN'])
            with self.assertRaises(LookupError):
                open_comparison_group(store, revision_id + 100, ())
            group_id = self.groups['single']
            with self.assertRaises(LookupError):
                issue_comparison_packet(store, 'missing-group', revision_id)
            with self.assertRaises(LookupError):
                issue_comparison_packet(store, group_id, revision_id + 100)
            # a revision of another recording cannot join the group
            foreign = self.tied_revisions[0]
            with self.assertRaises(ValueError):
                issue_comparison_packet(store, group_id, foreign)

    def test_reopened_source_keeps_issuing_with_an_independent_group_identity(self):
        with closing(sqlite3.connect(self.source_path)) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            first_group = self.groups['single']
            second_group = open_comparison_group(
                store, self.revisions['single']['first'], self.fixture['single']['public'])
            self.assertNotEqual(first_group, second_group)
            self.assertTrue(second_group)
            wire, registration = issue_comparison_packet(
                store, second_group, self.revisions['single']['first'])
            self.assertEqual(
                get_issue_registration(source, registration.issue_id), registration)
            self.assertEqual(read_envelope(wire).version, V2)

    def test_group_limits_allow_six_public_main_and_twelve_secondary(self):
        with closing(sqlite3.connect(':memory:')) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            main = [[f'M{index}', index, 0] for index in range(7)]
            secondary = [[f'S{index}', index, 0] for index in range(12)]
            revision = freeze_run(store, import_run(store, 'LIMIT', main, secondary))
            group_id = open_comparison_group(
                store, revision, [f'M{index}' for index in range(6)])
            self.assertTrue(group_id)
            with self.assertRaises(ValueError):
                open_comparison_group(
                    store, revision, [f'M{index}' for index in range(7)])
            wide_secondary = secondary + [['SX', 13, 0]]
            wide_revision = freeze_run(store, import_run(
                store, 'LIMIT-WIDE', main, wide_secondary))
            with self.assertRaises(ValueError):
                open_comparison_group(store, wide_revision, ())

    def test_adjudication_matches_an_independent_full_track_oracle(self):
        from itertools import combinations

        def oracle(case, left_name, right_name):
            variants = {row['name']: row for row in case['revisions']}
            secondary = case['secondary']
            plans = []
            for name in (left_name, right_name):
                variant = variants[name]
                left_width, right_width = variant['window']
                readings = variant['readings']
                main = [(sid, seq, readings.get(sid, value))
                        for sid, seq, value in case['main']]
                feasible = {}
                for indices in combinations(range(len(secondary)), len(main)):
                    total = 0
                    for (sid, seq, reading), index in zip(main, indices):
                        _, time, value = secondary[index]
                        if not seq - left_width <= time <= seq + right_width:
                            break
                        total += abs(reading - value)
                    else:
                        feasible[indices] = total
                plans.append(feasible)
            shared = set(plans[0]) & set(plans[1])
            if not shared:
                return None, None
            positions = min(
                shared,
                key=lambda indices: (
                    max(plans[0][indices], plans[1][indices]),
                    tuple(indices[slot] for slot in public_slots),
                ))
            upper = max(plans[0][positions], plans[1][positions])
            pairs = tuple(
                (case['public'][rank], secondary[positions[slot]][0])
                for rank, slot in enumerate(public_slots))
            return upper, pairs

        case = self.fixture['single']
        public_slots = [
            index for index, sample in enumerate(case['main'])
            if sample[0] in set(case['public'])]
        _, receipts, reports = self._night()
        received = self._receive_all(receipts)
        for left_name, right_name in (
            ('first', 'second'), ('first', 'third'),
            ('left', 'right'), ('first', 'right'),
        ):
            with self.subTest(selection=(left_name, right_name)):
                expected = oracle(case, left_name, right_name)
                report = sign_shared_setup(
                    receipts, reports,
                    received[('single', left_name)], received[('single', right_name)])
                self.assertEqual((report.upper_cost, report.pairs), expected)

    def test_empty_tracks_produce_a_zero_cost_empty_pairing(self):
        with closing(sqlite3.connect(':memory:')) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            first_revision = freeze_run(store, import_run(store, 'EMPTY', [], []))
            second_revision = freeze_run(store, import_run(
                store, 'EMPTY', [], [], corrects=first_revision))
            group_id = open_comparison_group(store, first_revision, ())
            first_packet = issue_comparison_packet(store, group_id, first_revision)
            second_packet = issue_comparison_packet(store, group_id, second_revision)
        with closing(sqlite3.connect(':memory:')) as night:
            receipts, reports = ReceiptStore(night), ReportStore(night)
            receipts.initialize()
            reports.initialize()
            first = receive_packet(receipts, *first_packet)
            second = receive_packet(receipts, *second_packet)
            report = sign_shared_setup(receipts, reports, first, second)
            self.assertEqual((report.upper_cost, report.pairs), (0, ()))
            body = json.loads(read_envelope(first_packet[0]).body)
            self.assertEqual(body['pairings'], [{'positions': [], 'total_cost': 0}])


if __name__ == '__main__':
    unittest.main()
