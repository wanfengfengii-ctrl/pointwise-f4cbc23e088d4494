from dataclasses import dataclass

from intake.receipts import Receipt
from intake.verify_comparison import VerifiedComparison
from issue.envelope import V2


@dataclass(frozen=True, slots=True)
class SharedSetupResult:
    upper_cost: int | None
    pairs: tuple[tuple[str, str], ...] | None


def _require_comparison(receipt: Receipt | None) -> VerifiedComparison:
    if receipt is None:
        raise LookupError('unknown receipt')
    if receipt.version != V2 or receipt.comparison is None:
        raise ValueError('a shared setup report requires two V2 comparison packets')
    return receipt.comparison


def adjudicate_shared_setup(first: Receipt, second: Receipt) -> SharedSetupResult:
    left = _require_comparison(first)
    right = _require_comparison(second)

    if left.group_id != right.group_id:
        raise ValueError('the two packets come from different comparison groups')
    if left.revision_id == right.revision_id:
        raise ValueError('the two packets must use different frozen revisions')
    if left.run_id != right.run_id:
        raise ValueError('the two packets describe different recordings')
    if left.secondary_ids != right.secondary_ids:
        raise ValueError('the two packets do not share the same secondary track')
    if left.main_count != right.main_count or left.public_slots != right.public_slots \
            or left.main_ids != right.main_ids:
        raise ValueError('the two packets do not share the same group layout')

    right_costs = {record.positions: record.total_cost for record in right.pairings}
    candidates = []
    for record in left.pairings:
        other = right_costs.get(record.positions)
        if other is None:
            continue
        upper = max(record.total_cost, other)
        public_projection = tuple(record.positions[slot] for slot in left.public_slots)
        candidates.append((upper, public_projection, record.positions))

    if not candidates:
        return SharedSetupResult(None, None)

    upper, _, positions = min(candidates)
    if not left.public_slots:
        return SharedSetupResult(upper, ())
    pairs = tuple(
        (left.main_ids[rank], left.secondary_ids[positions[slot]])
        for rank, slot in enumerate(left.public_slots)
    )
    return SharedSetupResult(upper, pairs)
