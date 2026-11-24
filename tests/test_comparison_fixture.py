import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from intake.receipts import ReceiptStore
from intake.receive import receive_packet
from issue.register import initialize_issue_store, issue_packet
from recording.import_run import import_run
from recording.revision_store import RevisionStore
from recording.revisions import freeze_run
from review.publish import sign_review
from review.report_store import ReportStore


class ComparisonFixtureTests(unittest.TestCase):
    def test_v1_single_revision_reports_keep_the_same_public_result(self):
        path = Path(__file__).resolve().parents[1] / "samples" / "setup_comparison.json"
        data = json.loads(path.read_text(encoding="utf-8"))["single"]
        packets = []
        with closing(sqlite3.connect(":memory:")) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            parent = None
            for variant in data["revisions"]:
                main = [(sample_id, sequence, variant["readings"].get(sample_id, value))
                        for sample_id, sequence, value in data["main"]]
                draft = import_run(store, data["run_id"], main, data["secondary"],
                                   corrects=parent, window=variant["window"])
                parent = freeze_run(store, draft)
                packets.append(issue_packet(store, parent, data["public"]))

        with closing(sqlite3.connect(":memory:")) as night:
            receipts, reports = ReceiptStore(night), ReportStore(night)
            receipts.initialize()
            reports.initialize()
            for name, packet in zip((row["name"] for row in data["revisions"]), packets):
                with self.subTest(revision=name):
                    receipt_id = receive_packet(receipts, *packet)
                    evidence = receipts.get_receipt(receipt_id).evidence
                    self.assertEqual(tuple((row.start, row.end, row.cost) for row in evidence.rows), (
                        (None, (0, 0), 0), ((0, 0), (1, 3), 0), ((1, 3), None, 0),
                    ))
                    report = sign_review(receipts, reports, receipt_id)
                    self.assertEqual((report.total_cost, report.pairs), (0, (("A", "U"), ("B", "V"))))
