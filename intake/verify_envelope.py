from dataclasses import dataclass

from issue.envelope import IssueRegistration, body_digest, read_envelope


@dataclass(frozen=True, slots=True)
class VerifiedEnvelope:
    registration: IssueRegistration
    wire: bytes
    body: bytes
    version: int


def verify_envelope(wire: bytes, registration: IssueRegistration) -> VerifiedEnvelope:
    if not isinstance(registration, IssueRegistration):
        raise ValueError('the original issue registration is required')
    if type(registration.issue_id) is not int or type(registration.revision_id) is not int:
        raise ValueError('registration requires integer issue and revision ids')
    if type(registration.run_id) is not str or not registration.run_id.strip():
        raise ValueError('invalid registered recording id')

    envelope = read_envelope(wire)
    if envelope.issue_id != registration.issue_id or envelope.body_sha256 != registration.body_sha256:
        raise ValueError('packet does not match the issue registration')
    if body_digest(envelope.body) != registration.body_sha256:
        raise ValueError('packet body digest mismatch')
    return VerifiedEnvelope(registration, wire, envelope.body, envelope.version)
