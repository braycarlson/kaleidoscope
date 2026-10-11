from __future__ import annotations

import os

from hypothesis import HealthCheck, settings


ENVIRONMENT_EXAMPLES = 'FUZZ_CASES'
EXAMPLES_DEFAULT = 60
EXAMPLES_LIMIT = 100_000


def examples_max() -> int:
    configured = (os.environ.get(ENVIRONMENT_EXAMPLES) or '').strip()

    if not configured:
        return EXAMPLES_DEFAULT

    if not configured.isdecimal():
        message = f'{ENVIRONMENT_EXAMPLES} must be a positive integer, received {configured!r}'
        raise ValueError(message)

    examples = int(configured)

    if not 1 <= examples <= EXAMPLES_LIMIT:
        message = f'{ENVIRONMENT_EXAMPLES} must be from 1 to {EXAMPLES_LIMIT}, received {examples}'
        raise ValueError(message)

    return examples


fuzz_settings = settings(
    deadline=None,
    max_examples=examples_max(),
    suppress_health_check=[
        HealthCheck.data_too_large,
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
    ],
)
