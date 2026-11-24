import sqlite3

from alignment.candidates import build_candidates
from alignment.reference import preview
from recording.import_run import import_run
from recording.revisions import freeze_run, get_frozen_revision
from tests.support import ArchiveCase, JOINT, corrected_secondary, freeze_sample, reject_commit, sample


class RecordingTests(ArchiveCase):
    def test_window_edges_and_zero_cost_witness(self):
        data = sample()
        with self.source() as store:
            revision = freeze_sample(store, data)
            snapshot = get_frozen_revision(store, revision)
            layers = build_candidates(snapshot)
            self.assertEqual([
                [snapshot.secondary[c.secondary_index].sample_id for c in layer] for layer in layers
            ], [['1', '2'], ['2', '3', '4'], ['4', '5']])
            witness = preview(store, revision)
            self.assertEqual(witness.total_cost, 0)
            self.assertEqual(witness.provenance.run_id, data['run_id'])
            self.assertEqual(witness.provenance.revision_id, revision)
            self.assertEqual([(p.main.sample_id, p.secondary.sample_id, p.cost) for p in witness.pairs], [
                ('A', '1', 0), ('H', '2', 0), ('B', '4', 0),
            ])
            self.assertEqual(preview(store, revision, JOINT).total_cost, 5)

    def test_frozen_values_and_provenance_survive_correction(self):
        data = sample()
        revised = [[sid, sequence, 13 if sid in {'1', '2'} else reading]
                   for sid, sequence, reading in data['secondary']]
        with self.source() as store:
            original = freeze_sample(store, data)
            before = preview(store, original)
            correction = freeze_sample(store, data, corrects=original, secondary=revised)
            self.assertEqual(freeze_run(store, original), original)
        with self.source() as store:
            self.assertEqual(preview(store, original), before)
            after = preview(store, correction)
            self.assertEqual(after.provenance.corrects, original)
            self.assertEqual(after.total_cost, 3)
            self.assertEqual(after.pairs[0].secondary.reading, 13)
            self.assertEqual(before.pairs[0].secondary.reading, 10)

    def test_legal_online_anchors_can_have_no_full_path(self):
        data = sample()
        with self.source() as store:
            revision = freeze_sample(store, data, secondary=corrected_secondary(data))
            self.assertEqual(preview(store, revision, JOINT[:1]).total_cost, 0)
            self.assertEqual(preview(store, revision, JOINT[1:]).total_cost, 0)
            self.assertIsNone(preview(store, revision, JOINT))
            with self.assertRaises(ValueError):
                preview(store, revision, [('H', '3')])
            with self.assertRaises(LookupError):
                preview(store, revision + 1)

    def test_rejected_drafts_do_not_modify_the_frozen_record(self):
        data = sample()
        bad_tracks = (
            [['A', 1, 10], ['A', 4, 10]],
            [['A', 4, 10], ['B', 1, 10]],
            [['A', 1, 10], ['B', 1, 10]],
            [['A', 1]],
            [['A', 1, 10.0]],
            [['A', 1, True]],
            [['', 1, 10]],
        )
        with self.source() as store:
            original = freeze_sample(store, data)
            before = get_frozen_revision(store, original)
            for bad in bad_tracks:
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    import_run(store, data['run_id'], bad, data['secondary'], corrects=original)
                self.assertIsNone(store.load_revision(original + 1))
            with self.assertRaises(ValueError):
                import_run(store, 'OTHER', data['main'], data['secondary'], corrects=original)
            with self.assertRaises(ValueError):
                import_run(store, data['run_id'], data['main'], data['secondary'], window=(2, -1))
            self.assertIsNone(store.load_revision(original + 1))
            next_revision = freeze_sample(store, data, corrects=original, secondary=corrected_secondary(data))
            self.assertEqual(next_revision, original + 1)
            self.assertEqual(get_frozen_revision(store, next_revision).corrects, original)
            self.assertEqual(get_frozen_revision(store, original), before)

    def test_init_preserves_operator_changes_and_drafts(self):
        with self.source() as store:
            draft = import_run(store, 'ZERO', [('A', 5, 0)], [('S', 7, 0)], window=(0, 2))
            store.connection.execute('CREATE TABLE operator_notes (note TEXT)')
            with store.connection:
                store.connection.execute('INSERT INTO operator_notes VALUES (?)', ('reviewed',))
                store.connection.execute('UPDATE operator_notes SET note = ?', ('reviewed by day shift',))
            store.initialize()
            with self.assertRaises(LookupError):
                preview(store, draft)
        with self.source() as store:
            self.assertEqual(store.connection.execute('SELECT note FROM operator_notes').fetchone(),
                             ('reviewed by day shift',))
            self.assertEqual(freeze_run(store, draft), draft)
            self.assertEqual(get_frozen_revision(store, draft).window, (0, 2))
            self.assertEqual(preview(store, draft).total_cost, 0)

    def test_freeze_commit_refusal_keeps_draft_available(self):
        data = sample()
        with self.source() as store:
            draft = import_run(store, data['run_id'], data['main'], data['secondary'])
            with reject_commit(store.connection) as refused:
                with self.assertRaises(sqlite3.DatabaseError):
                    freeze_run(store, draft)
            self.assertEqual(refused, ['COMMIT'])
        with self.source() as store:
            self.assertFalse(store.load_revision(draft).frozen)
            self.assertEqual(freeze_run(store, draft), draft)
