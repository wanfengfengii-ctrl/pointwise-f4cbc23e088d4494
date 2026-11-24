from intake.receipts import ReceiptStore
from intake.verify_envelope import verify_envelope
from intake.verify_evidence import verify_evidence
from issue.envelope import IssueRegistration


def receive_packet(store: ReceiptStore, packet: bytes, registration: IssueRegistration) -> int:
    envelope = verify_envelope(packet, registration)
    verify_evidence(envelope)
    return store.record_receipt(envelope)
