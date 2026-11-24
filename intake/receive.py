from intake.receipts import ReceiptStore
from intake.verify_comparison import verify_comparison_body
from intake.verify_envelope import verify_envelope
from intake.verify_evidence import verify_evidence
from issue.envelope import V1, V2, IssueRegistration


def receive_packet(store: ReceiptStore, packet: bytes, registration: IssueRegistration) -> int:
    envelope = verify_envelope(packet, registration)
    if envelope.version == V1:
        verify_evidence(envelope)
    elif envelope.version == V2:
        verify_comparison_body(envelope)
    else:  # pragma: no cover - envelope verification rejects other versions
        raise ValueError('unsupported packet version')
    return store.record_receipt(envelope)
