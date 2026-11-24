from review.report_store import ReportStore, SignedReport


def get_report(store: ReportStore, report_id: int) -> SignedReport | None:
    return store.load_report(report_id)
