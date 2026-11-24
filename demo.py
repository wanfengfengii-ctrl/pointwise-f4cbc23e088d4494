import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from alignment.reference import preview
from intake.receipts import ReceiptStore
from intake.receive import receive_packet
from issue.register import (
    get_issue_registration,
    initialize_issue_store,
    issue_comparison_packet,
    issue_packet,
    open_comparison_group,
)
from recording.import_run import import_run
from recording.revision_store import RevisionStore
from recording.revisions import freeze_run
from review.publish import sign_review, sign_shared_setup
from review.report_store import ReportStore
from review.retrieve import get_report, get_shared_setup_report


SAMPLES = Path(__file__).resolve().parent / 'samples'


def load_recording(name):
    return json.loads((SAMPLES / f'{name}.json').read_text(encoding='utf-8'))


def import_comparison_case(store, case):
    parent = None
    revisions = {}
    for variant in case['revisions']:
        main = [(sample_id, sequence, variant['readings'].get(sample_id, value))
                for sample_id, sequence, value in case['main']]
        draft = import_run(store, case['run_id'], main, case['secondary'],
                           corrects=parent, window=variant['window'])
        parent = freeze_run(store, draft)
        revisions[variant['name']] = parent
    return revisions


def prepare_packet(store, data, *, corrects=None, secondary=None):
    if secondary is None:
        secondary = data['secondary']
    draft = import_run(store, data['run_id'], data['main'], secondary, corrects=corrects)
    revision = freeze_run(store, draft)
    reference = preview(store, revision)
    if reference is None:
        raise RuntimeError('the demo recording must have an unconditional path')
    packet, registration = issue_packet(store, revision, data['public'])
    saved_registration = get_issue_registration(store.connection, registration.issue_id)
    if saved_registration != registration:
        raise RuntimeError('the issued packet registration was not retained')
    print(f'{data["run_id"]} revision {revision} online cost {reference.total_cost}, issue {registration.issue_id}')
    return revision, (packet, saved_registration)


def result(report):
    return {'total_cost': report.total_cost, 'pairs': report.pairs}


def show_scenario(case_id, inputs, expected, actual, saved, oracle):
    if result(actual) != expected or saved != actual:
        raise RuntimeError(f'{case_id} gave an unexpected result or stored snapshot')
    payload = {
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': result(actual),
        'downstream_expected': {'receipt_id': actual.receipt_id, 'result': expected},
        'downstream_actual': {'receipt_id': saved.receipt_id, 'result': result(saved)},
        'code_paths': ['issue/evidence.py', 'intake/receive.py', 'review/reconcile.py',
                       'review/report_store.py', 'review/retrieve.py'],
        'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(payload, ensure_ascii=False, sort_keys=True))


def show_shared_scenario(case_id, actual, expected, sources, group_id, run_id):
    if (actual.upper_cost, actual.pairs) != expected:
        raise RuntimeError(f'{case_id} gave an unexpected shared setup result')
    payload = {
        'case_id': case_id,
        'group_id': group_id,
        'run_id': run_id,
        'expected': {'upper_cost': expected[0], 'pairs': expected[1]},
        'actual': {'upper_cost': actual.upper_cost, 'pairs': actual.pairs},
        'sources': [
            {
                'receipt_id': source.receipt_id,
                'issue_id': source.issue_id,
                'revision_id': source.revision_id,
                'body_sha256': source.body_sha256,
            }
            for source in sources
        ],
        'code_paths': ['issue/comparison_groups.py', 'issue/register.py',
                       'intake/verify_comparison.py', 'review/shared_setup.py',
                       'review/report_store.py', 'review/retrieve.py'],
    }
    print('POINTWISE_SHARED_SETUP ' + json.dumps(payload, ensure_ascii=False, sort_keys=True))


def run_shared_setup_demo():
    fixture = load_recording('setup_comparison')['single']
    with TemporaryDirectory(prefix='vibration-shared-') as directory:
        root = Path(directory)
        source_path = root / 'station.sqlite'
        night_path = root / 'night.sqlite'

        with closing(sqlite3.connect(source_path)) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            revisions = import_comparison_case(store, fixture)
            group_id = open_comparison_group(store, revisions['first'], fixture['public'])
            packets = {
                name: issue_comparison_packet(store, group_id, revision_id)
                for name, revision_id in revisions.items()
            }
            print(f"comparison group {group_id} opened on {fixture['run_id']}, "
                  f"revisions {sorted(revisions.values())} issued independently")

        # source station shuts down: the isolated library only holds wires and registrations
        source_path.rename(root / 'station-offline.sqlite')
        report_ids = {}
        with closing(sqlite3.connect(night_path)) as night:
            receipts, reports = ReceiptStore(night), ReportStore(night)
            receipts.initialize()
            reports.initialize()
            received = {
                name: receive_packet(receipts, wire, registration)
                for name, (wire, registration) in packets.items()
            }
            selections = [
                ('shared-first-second', 'first', 'second', 4, (('A', 'U'), ('B', 'V'))),
                ('shared-first-third', 'first', 'third', 0, (('A', 'U'), ('B', 'V'))),
                ('shared-left-right', 'left', 'right', None, None),
                ('shared-first-right', 'first', 'right', 4, (('A', 'U'), ('B', 'V'))),
            ]
            for case_id, left_name, right_name, cost, pairs in selections:
                report = sign_shared_setup(
                    receipts, reports, received[left_name], received[right_name])
                report_ids[case_id] = report.report_id
                show_shared_scenario(
                    case_id, report, (cost, pairs), report.sources,
                    report.group_id, report.run_id)

        # morning shift reopens the isolated library and retrieves stored values by report id
        with closing(sqlite3.connect(night_path)) as night:
            reports = ReportStore(night)
            reports.initialize()
            for case_id, _, _, cost, pairs in selections:
                reopened = get_shared_setup_report(reports, report_ids[case_id])
                if reopened is None or (reopened.upper_cost, reopened.pairs) != (cost, pairs):
                    raise RuntimeError(f'{case_id} could not be retrieved after reopening')
            unknown = get_shared_setup_report(reports, max(report_ids.values()) + 100)
            if unknown is not None:
                raise RuntimeError('an unknown report id must return None')
            print('isolated library reopened; all shared setup reports retrieved by report id, '
                  f'unknown id returns None: {report_ids}')


def main():
    data = load_recording('windowed_run')
    tied = load_recording('tied_run')
    anchors = (('A', '2'), ('B', '4'))
    reduced = [row for row in data['secondary'] if row[0] != data['remove_secondary']]
    with TemporaryDirectory(prefix='vibration-archive-') as directory:
        root = Path(directory)
        with closing(sqlite3.connect(root / 'station.sqlite')) as source:
            store = RevisionStore(source)
            store.initialize()
            initialize_issue_store(source)
            original, first = prepare_packet(store, data)
            _, second = prepare_packet(store, data, corrects=original, secondary=reduced)
            _, third = prepare_packet(store, tied)

        with closing(sqlite3.connect(root / 'night.sqlite')) as night:
            receipts, reports = ReceiptStore(night), ReportStore(night)
            receipts.initialize()
            reports.initialize()
            first_id = receive_packet(receipts, *first)
            single_a = sign_review(receipts, reports, first_id, anchors[:1])
            single_b = sign_review(receipts, reports, first_id, anchors[1:])
            if (single_a.total_cost, single_b.total_cost) != (0, 0):
                raise RuntimeError('the two individual tickets must each admit a zero-cost path')
            print(f'receipt {first_id} single-anchor costs {single_a.total_cost}, {single_b.total_cost}')
            original_report = sign_review(receipts, reports, first_id, anchors)
            revised_report = sign_review(receipts, reports, receive_packet(receipts, *second), anchors)
            tied_report = sign_review(receipts, reports, receive_packet(receipts, *third))

        with closing(sqlite3.connect(root / 'night.sqlite')) as night:
            reports = ReportStore(night)
            reports.initialize()
            show_scenario('v5', {'main': data['main'], 'secondary': data['secondary'], 'anchors': anchors},
                          {'total_cost': 5, 'pairs': anchors}, original_report,
                          get_report(reports, original_report.report_id),
                          'Between secondary positions 2 and 4 only sample 3 is available for H. Its difference is 5.')
            show_scenario('v6', {'main': data['main'], 'secondary': reduced, 'anchors': anchors},
                          {'total_cost': None, 'pairs': None}, revised_report,
                          get_report(reports, revised_report.report_id),
                          'Removing sample 3 leaves no secondary position strictly between the two anchors.')
            show_scenario('v8', {'main': tied['main'], 'secondary': tied['secondary'], 'public': tied['public']},
                          {'total_cost': 5, 'pairs': (('A', 'S2'), ('B', 'S11'))}, tied_report,
                          get_report(reports, tied_report.report_id),
                          'Hidden endpoints cost 2 and 3. S2 precedes the equally priced S10 in recorder order.')

    run_shared_setup_demo()


if __name__ == '__main__':
    main()
