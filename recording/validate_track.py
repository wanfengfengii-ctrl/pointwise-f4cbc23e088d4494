from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Sample:
    sample_id: str
    sequence: int
    reading: int


Track = tuple[Sample, ...]


def validate_track(name: str, samples: Iterable) -> Track:
    """Validate and preserve the order supplied by the recorder."""
    if isinstance(samples, (str, bytes, Mapping)):
        raise ValueError(f'{name} must be a sequence of samples')
    try:
        rows = iter(samples)
    except TypeError as error:
        raise ValueError(f'{name} must be a sequence of samples') from error

    seen = set()
    previous = None
    track = []
    for position, row in enumerate(rows, start=1):
        location = f'{name} sample {position}'
        if isinstance(row, Sample):
            sample = row
        elif isinstance(row, (list, tuple)) and len(row) == 3:
            sample = Sample(*row)
        else:
            raise ValueError(f'{location} requires an id, sequence and reading')
        if type(sample.sample_id) is not str or not sample.sample_id.strip():
            raise ValueError(f'{location} has an invalid sample id')
        if type(sample.sequence) is not int or type(sample.reading) is not int:
            raise ValueError(f'{location} requires an integer sequence and reading')
        if sample.sample_id in seen:
            raise ValueError(f'{location} repeats sample id {sample.sample_id!r}')
        if previous is not None and sample.sequence <= previous:
            raise ValueError(f'{location} is outside the recorder sequence order')
        seen.add(sample.sample_id)
        previous = sample.sequence
        track.append(sample)
    return tuple(track)
