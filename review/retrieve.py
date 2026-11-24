from review.report_store import ReportStore, SignedReport


def get_report(store: ReportStore, report_id: int) -> SignedReport | None:
    return store.load_report(report_id)


def get_shared_setup_report(store: ReportStore, report_id: int):
    return store.load_shared_setup_report(report_id)
