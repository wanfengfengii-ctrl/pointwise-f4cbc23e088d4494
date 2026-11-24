import base64
import hashlib
import json
from dataclasses import dataclass


V1 = 1
V2 = 2
SUPPORTED_VERSIONS = (V1, V2)


@dataclass(frozen=True, slots=True)
class PacketEnvelope:
    version: int
    issue_id: int
    body_sha256: str
    body: bytes


@dataclass(frozen=True, slots=True)
class IssueRegistration:
    issue_id: int
    run_id: str
    revision_id: int
    body_sha256: str


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def seal_envelope(issue_id: int, body: bytes, version: int = V1) -> bytes:
    if type(issue_id) is not int or not 0 < issue_id < 2**63 or type(body) is not bytes:
        raise ValueError('invalid issue id or body')
    if version not in SUPPORTED_VERSIONS:
        raise ValueError('unsupported envelope version')
    fields = {
        'version': version,
        'issue_id': issue_id,
        'sha256': body_digest(body),
        'body': base64.b64encode(body).decode('ascii'),
    }
    return json.dumps(fields, separators=(',', ':'), sort_keys=True).encode('utf-8')


def read_envelope(wire: bytes) -> PacketEnvelope:
    fields = read_json_object(wire)
    if fields.keys() != {'version', 'issue_id', 'sha256', 'body'}:
        raise ValueError('invalid envelope fields')
    if type(fields['version']) is not int or fields['version'] not in SUPPORTED_VERSIONS:
        raise ValueError('unsupported envelope version')
    version = fields['version']
    issue_id = fields['issue_id']
    if type(issue_id) is not int or not 0 < issue_id < 2**63:
        raise ValueError('invalid envelope issue id')
    digest = fields['sha256']
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('invalid envelope digest')
    encoded = fields['body']
    if type(encoded) is not str:
        raise ValueError('invalid encoded body')
    return PacketEnvelope(version, issue_id, digest, base64.b64decode(encoded, validate=True))


def read_json_object(wire: bytes) -> dict:
    if type(wire) is not bytes:
        raise ValueError('packet data must be bytes')

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate packet field {key!r}')
            result[key] = value
        return result

    data = json.loads(wire.decode('utf-8'), object_pairs_hook=unique_object)
    if type(data) is not dict:
        raise ValueError('packet data must be an object')
    return data
