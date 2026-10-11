from __future__ import annotations

import pytest

from kaleidoscope.context import KaleidoscopeContext


def test_context_carries_the_request_kind_and_server_kind() -> None:
    context = KaleidoscopeContext(asgi=True, is_ajax=True)

    assert context.is_ajax
    assert context.asgi
    assert context.state == {}


def test_context_request_ids_are_unique_hex_strings() -> None:
    identifiers = {KaleidoscopeContext().request_id for _ in range(200)}

    assert len(identifiers) == 200

    for identifier in identifiers:
        assert len(identifier) == 32
        assert int(identifier, 16) >= 0


def test_context_state_is_not_shared_between_instances() -> None:
    first = KaleidoscopeContext()
    second = KaleidoscopeContext()
    first.state['key'] = 'value'

    assert second.state == {}


@pytest.mark.parametrize(
    ('field', 'value', 'error', 'pattern'),
    [
        ('asgi', 'yes', TypeError, 'asgi must be a bool'),
        ('is_ajax', 1, TypeError, 'is_ajax must be a bool'),
        ('panels', (), TypeError, 'panels must be a list'),
        ('request_id', 7, TypeError, 'request_id must be text'),
        ('request_id', '', ValueError, 'request_id must not be empty'),
        ('started_ns', True, TypeError, 'started_ns must be an integer, not a bool'),
        ('started_ns', 1.5, TypeError, 'started_ns must be an integer'),
        ('state', [], TypeError, 'state must be a dict'),
    ],
)
def test_context_refuses_a_field_of_the_wrong_kind(
    field: str,
    value: object,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        KaleidoscopeContext(**{field: value})
