from collections.abc import Iterable

from intake.receipts import ReceiptStore
from review.anchors import normalize_anchors
from review.reconcile import reconcile
from review.report_store import ReportStore, SharedSetupSourceRecord, SignedReport
from review.shared_setup import adjudicate_shared_setup


def sign_review(
    receipts: ReceiptStore, reports: ReportStore, receipt_id: int,
    anchors: Iterable[tuple[str, str]] = (),
) -> SignedReport:
    receipt = receipts.get_receipt(receipt_id)
    if receipt is None:
        raise LookupError(f'unknown receipt {receipt_id}')
    evidence = receipt.evidence
    if evidence is None:
        raise ValueError('sign_review requires a V1 packet')
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


def sign_shared_setup(
    receipts: ReceiptStore, reports: ReportStore,
    first_receipt_id: int, second_receipt_id: int,
):
    first = receipts.get_receipt(first_receipt_id)
    if first is None:
        raise LookupError(f'unknown receipt {first_receipt_id}')
    second = receipts.get_receipt(second_receipt_id)
    if second is None:
        raise LookupError(f'unknown receipt {second_receipt_id}')
    result = adjudicate_shared_setup(first, second)
    sources = tuple(
        SharedSetupSourceRecord(
            receipt.receipt_id, receipt.registration.issue_id,
            receipt.registration.revision_id, receipt.registration.body_sha256,
        )
        for receipt in (first, second)
    )
    group_id = first.comparison.group_id
    return reports.commit_shared_setup_report(
        group_id=group_id, run_id=first.registration.run_id,
        sources=sources, upper_cost=result.upper_cost, pairs=result.pairs,
    )
