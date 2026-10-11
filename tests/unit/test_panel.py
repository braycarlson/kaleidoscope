from __future__ import annotations

import pytest

from kaleidoscope.panel import Panel, ServerTimingMetric


class _PanelBare(Panel):
    panel_id = 'bare'
    title = 'Bare'

    def get_data(self) -> dict:
        return {}

    def get_summary(self) -> str:
        return ''


@pytest.mark.parametrize(
    ('arguments', 'error', 'pattern'),
    [
        ({'key': 7, 'description': '', 'duration': 1.0}, TypeError, 'key must be text'),
        ({'key': '', 'description': '', 'duration': 1.0}, ValueError, 'key must not be empty'),
        ({'key': 'k', 'description': None, 'duration': 1.0}, TypeError, 'description must be text'),
        ({'key': 'k', 'description': '', 'duration': True}, TypeError, 'not a bool'),
        ({'key': 'k', 'description': '', 'duration': 'slow'}, TypeError, 'must be a number'),
    ],
)
def test_a_metric_refuses_a_field_of_the_wrong_kind(
    arguments: dict,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        ServerTimingMetric(**arguments)


def test_a_metric_accepts_an_integer_duration() -> None:
    metric = ServerTimingMetric(key='total', description='Total', duration=5)

    assert metric.duration == 5


@pytest.mark.parametrize(
    ('attribute', 'value', 'pattern'),
    [
        ('panel_id', None, 'panel_id must be text'),
        ('title', 3, 'title must be text'),
        ('default_enabled', 'yes', 'default_enabled must be a bool'),
        ('follows_view', 1, 'follows_view must be a bool'),
        ('isolate', None, 'isolate must be a bool'),
    ],
)
def test_a_panel_class_with_a_malformed_attribute_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    value: object,
    pattern: str,
) -> None:
    monkeypatch.setattr(_PanelBare, attribute, value)

    with pytest.raises(TypeError, match=f'_PanelBare.{pattern}'):
        _PanelBare()


def test_a_panel_starts_in_its_default_state() -> None:
    panel = _PanelBare()

    assert panel.enabled is True
    assert panel.get_server_timing(None) == []  # ty:ignore[invalid-argument-type]
    assert panel.handle_action('any', None) is None  # ty:ignore[invalid-argument-type]
