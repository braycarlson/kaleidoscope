from __future__ import annotations

import contextlib
import json

import pytest

from hypothesis import given
from hypothesis import strategies as st

from kaleidoscope.serializer import (
    CONTEXT_CHILD_PREVIEW_LENGTH_MAX,
    has_children,
    preview,
    resolve_path,
    serialize,
)

from tests.fuzz.settings import fuzz_settings
from tests.fuzz.strategies import TEXTS_HOSTILE, VALUES_NESTED, json_strict_load


pytestmark = pytest.mark.fuzz
STEP_KINDS = st.sampled_from(['key', 'attr', 'item', 'other', None, 5])

STEPS = st.lists(
    st.one_of(
        st.fixed_dictionaries({
            'index': st.one_of(st.integers(), TEXTS_HOSTILE, st.none()),
            'kind': STEP_KINDS,
            'name': st.one_of(TEXTS_HOSTILE, st.integers(), st.none()),
        }),
        TEXTS_HOSTILE,
        st.integers(),
        st.none(),
    ),
    max_size=6,
)


class _Hostile:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __bool__(self) -> bool:
        message = 'truthiness refused'
        raise RuntimeError(message)

    def __len__(self) -> int:
        message = 'length refused'
        raise RuntimeError(message)

    def __repr__(self) -> str:
        message = 'repr refused'
        raise RuntimeError(message)


VALUES = st.one_of(VALUES_NESTED, VALUES_NESTED.map(_Hostile))


@fuzz_settings
@given(value=VALUES)
def test_serialize_never_raises_and_answers_strict_json(value: object) -> None:
    serialized = serialize(value)
    text = json.dumps(serialized, allow_nan=False)

    assert isinstance(json_strict_load(text), dict)
    assert isinstance(serialized['type'], str)


@fuzz_settings
@given(value=VALUES)
def test_preview_never_raises_and_stays_bounded(value: object) -> None:
    text = preview(value)

    assert isinstance(text, str)
    assert len(text) <= CONTEXT_CHILD_PREVIEW_LENGTH_MAX
    assert has_children(value) in (True, False)


@fuzz_settings
@given(root=VALUES_NESTED, steps=STEPS)
def test_resolve_path_raises_only_lookup_errors(root: object, steps: list) -> None:
    with contextlib.suppress(AttributeError, IndexError, KeyError, TypeError, ValueError):
        resolve_path(root, steps)
