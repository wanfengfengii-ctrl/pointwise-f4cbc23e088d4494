from dataclasses import dataclass

from intake.verify_envelope import VerifiedEnvelope
from issue.envelope import read_json_object


Endpoint = tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    start: Endpoint
    end: Endpoint
    cost: int


@dataclass(frozen=True, slots=True)
class VerifiedEvidence:
    run_id: str
    revision_id: int
    main_ids: tuple[str, ...]
    secondary_ids: tuple[str, ...]
    rows: tuple[EvidenceRow, ...]


def _directory(value, field: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str or not item.strip() for item in value):
        raise ValueError(f'invalid {field} directory')
    if len(set(value)) != len(value):
        raise ValueError(f'duplicate ids in {field} directory')
    return tuple(value)


def _endpoint(value, main_count: int, secondary_count: int) -> Endpoint:
    if value is None:
        return None
    if type(value) is not list or len(value) != 2:
        raise ValueError('an evidence endpoint requires two directory indices')
    main, secondary = value
    if type(main) is not int or not 0 <= main < main_count:
        raise ValueError('evidence references an unknown public main sample')
    if type(secondary) is not int or not 0 <= secondary < secondary_count:
        raise ValueError('evidence references an unknown secondary sample')
    return main, secondary


def verify_evidence(verified: VerifiedEnvelope) -> VerifiedEvidence:
    body = read_json_object(verified.body)
    if body.keys() != {'run_id', 'revision_id', 'main', 'secondary', 'evidence'}:
        raise ValueError('invalid packet body fields')
    run_id, revision_id = body['run_id'], body['revision_id']
    registration = verified.registration
    if type(run_id) is not str or run_id != registration.run_id:
        raise ValueError('body recording id does not match its registration')
    if type(revision_id) is not int or not 0 < revision_id < 2**63 or revision_id != registration.revision_id:
        raise ValueError('body revision id does not match its registration')
    main = _directory(body['main'], 'main')
    secondary = _directory(body['secondary'], 'secondary')
    if type(body['evidence']) is not list:
        raise ValueError('invalid evidence records')

    rows = []
    seen = set()
    for raw in body['evidence']:
        if type(raw) is not list or len(raw) != 3:
            raise ValueError('evidence records require two endpoints and a cost')
        start = _endpoint(raw[0], len(main), len(secondary))
        end = _endpoint(raw[1], len(main), len(secondary))
        cost = raw[2]
        if type(cost) is not int or cost < 0:
            raise ValueError('evidence costs must be nonnegative integer ticks')
        if start is not None and end is not None:
            if start[0] >= end[0] or start[1] >= end[1]:
                raise ValueError('evidence endpoints must advance in directory order')
        key = start, end
        if key in seen:
            raise ValueError('duplicate evidence endpoints')
        seen.add(key)
        rows.append(EvidenceRow(start, end, cost))
    return VerifiedEvidence(run_id, revision_id, main, secondary, tuple(rows))
