import json

from issue.disclosure import Disclosure
from issue.evidence import Evidence
from recording.provenance import RevisionProvenance


def build_body(origin: RevisionProvenance, disclosure: Disclosure, evidence: Evidence) -> bytes:
    body = {
        'run_id': origin.run_id,
        'revision_id': origin.revision_id,
        'main': disclosure.main_ids,
        'secondary': disclosure.secondary_ids,
        'evidence': evidence,
    }
    return json.dumps(body, separators=(',', ':'), sort_keys=True).encode('utf-8')
