from collections.abc import Iterable

from intake.receipts import ReceiptStore
from review.anchors import normalize_anchors
from review.reconcile import reconcile
from review.report_store import ReportStore, SignedReport


def sign_review(
    receipts: ReceiptStore, reports: ReportStore, receipt_id: int,
    anchors: Iterable[tuple[str, str]] = (),
) -> SignedReport:
    receipt = receipts.get_receipt(receipt_id)
    if receipt is None:
        raise LookupError(f'unknown receipt {receipt_id}')
    evidence = receipt.evidence
    fixed = normalize_anchors(evidence, anchors)
    result = reconcile(evidence, fixed)
    recorded_anchors = tuple(
        (evidence.main_ids[anchor.main_index], evidence.secondary_ids[anchor.secondary_index])
        for anchor in fixed
    )
    origin = receipt.registration
    return reports.commit_report(
        receipt_id=receipt_id, issue_id=origin.issue_id, run_id=origin.run_id,
        revision_id=origin.revision_id, body_sha256=origin.body_sha256,
        anchors=recorded_anchors, total_cost=result.total_cost, pairs=result.pairs,
    )
