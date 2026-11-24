from dataclasses import dataclass

from intake.verify_envelope import VerifiedEnvelope
from issue.comparison_body import COMPARISON_BODY_FIELDS
from issue.envelope import read_json_object


@dataclass(frozen=True, slots=True)
class PairingRecord:
    positions: tuple[int, ...]
    total_cost: int


@dataclass(frozen=True, slots=True)
class VerifiedComparison:
    group_id: str
    run_id: str
    revision_id: int
    main_count: int
    public_slots: tuple[int, ...]
    main_ids: tuple[str, ...]
    secondary_ids: tuple[str, ...]
    pairings: tuple[PairingRecord, ...]


def _identifier_directory(value, field: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str or not item.strip() for item in value):
        raise ValueError(f'invalid {field} directory')
    if len(set(value)) != len(value):
        raise ValueError(f'duplicate ids in {field} directory')
    return tuple(value)


def verify_comparison_body(verified: VerifiedEnvelope) -> VerifiedComparison:
    body = read_json_object(verified.body)
    if tuple(sorted(body.keys())) != tuple(sorted(COMPARISON_BODY_FIELDS)):
        raise ValueError('invalid comparison body fields')

    group_id = body['group_id']
    if type(group_id) is not str or not group_id.strip():
        raise ValueError('invalid comparison group id')
    run_id = body['run_id']
    registration = verified.registration
    if type(run_id) is not str or run_id != registration.run_id:
        raise ValueError('body recording id does not match its registration')
    revision_id = body['revision_id']
    if type(revision_id) is not int or not 0 < revision_id < 2**63 \
            or revision_id != registration.revision_id:
        raise ValueError('body revision id does not match its registration')

    main_count = body['main_count']
    if type(main_count) is not int or main_count < 0:
        raise ValueError('invalid main sample count')

    main_ids = _identifier_directory(body['main'], 'main')
    secondary_ids = _identifier_directory(body['secondary'], 'secondary')
    raw_slots = body['public_slots']
    if type(raw_slots) is not list or any(type(slot) is not int for slot in raw_slots):
        raise ValueError('invalid public slot list')
    if len(raw_slots) != len(set(raw_slots)) or any(
        not 0 <= slot < main_count for slot in raw_slots
    ):
        raise ValueError('public slots must be distinct main positions')
    public_slots = tuple(sorted(raw_slots))
    if len(public_slots) != len(main_ids):
        raise ValueError('the public slots and main directory disagree')
    if tuple(raw_slots) != public_slots:
        raise ValueError('the main directory must follow the original recording order')

    raw_pairings = body['pairings']
    if type(raw_pairings) is not list:
        raise ValueError('invalid pairing records')
    pairings = []
    seen = set()
    for raw in raw_pairings:
        if type(raw) is not dict or tuple(sorted(raw.keys())) != ('positions', 'total_cost'):
            raise ValueError('each pairing needs positions and a total cost')
        positions = raw['positions']
        total_cost = raw['total_cost']
        if type(positions) is not list or any(type(index) is not int for index in positions):
            raise ValueError('pairing positions must be integers')
        if len(positions) != main_count:
            raise ValueError('each pairing must cover every main beat, including hidden beats')
        if any(not 0 <= index < len(secondary_ids) for index in positions):
            raise ValueError('pairing positions reference an unknown secondary sample')
        if any(left >= right for left, right in zip(positions, positions[1:])):
            raise ValueError('pairing positions must advance in secondary order')
        if type(total_cost) is not int or total_cost < 0:
            raise ValueError('pairing costs must be nonnegative integer ticks')
        key = tuple(positions)
        if key in seen:
            raise ValueError('duplicate pairing positions')
        seen.add(key)
        pairings.append(PairingRecord(key, total_cost))

    return VerifiedComparison(
        group_id, run_id, revision_id, main_count, public_slots,
        main_ids, secondary_ids, tuple(pairings),
    )
