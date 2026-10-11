from __future__ import annotations

import pytest

from django.test import override_settings

from kaleidoscope.checks import (
    _is_middleware_class,
    _is_subclass,
    check_ignore_paths,
    check_internal_ips,
    check_middleware,
    check_panels,
)


MIDDLEWARE_GZIP = 'django.middleware.gzip.GZipMiddleware'
MIDDLEWARE_KALEIDOSCOPE = 'kaleidoscope.middleware.KaleidoscopeMiddleware'
MIDDLEWARE_SESSION = 'django.contrib.sessions.middleware.SessionMiddleware'


def _identifiers(warnings: list) -> list[str]:
    return [warning.id for warning in warnings]


@pytest.mark.parametrize(
    ('middleware', 'expected'),
    [
        ([MIDDLEWARE_KALEIDOSCOPE], []),
        ([MIDDLEWARE_SESSION], ['kaleidoscope.W001']),
        ([MIDDLEWARE_KALEIDOSCOPE, MIDDLEWARE_KALEIDOSCOPE], ['kaleidoscope.W002']),
        ([MIDDLEWARE_KALEIDOSCOPE, MIDDLEWARE_GZIP], ['kaleidoscope.W003']),
        ([MIDDLEWARE_GZIP, MIDDLEWARE_KALEIDOSCOPE], []),
        (['no.such.Middleware', MIDDLEWARE_KALEIDOSCOPE], []),
    ],
)
def test_middleware_check_warns_about_a_missing_doubled_or_misplaced_toolbar(
    middleware: list[str],
    expected: list[str],
) -> None:
    with override_settings(MIDDLEWARE=middleware):
        assert _identifiers(check_middleware(None)) == expected


@pytest.mark.parametrize(
    ('callback', 'internal_ips', 'expected'),
    [
        (None, [], ['kaleidoscope.W004']),
        (None, ['127.0.0.1'], []),
        ('tests.testapp.visibility.toolbar_visible', [], []),
    ],
)
def test_internal_ips_check_warns_only_when_nothing_could_show_the_toolbar(
    callback: str | None,
    internal_ips: list[str],
    expected: list[str],
) -> None:
    with override_settings(KALEIDOSCOPE_SHOW_CALLBACK=callback, INTERNAL_IPS=internal_ips):
        assert _identifiers(check_internal_ips(None)) == expected


@pytest.mark.parametrize(
    ('panels', 'expected'),
    [
        (['kaleidoscope.panels.timer.TimerPanel'], []),
        (['kaleidoscope.panels.missing.Panel'], ['kaleidoscope.W005']),
        (['kaleidoscope.store.QueryStore'], ['kaleidoscope.W006']),
        (['kaleidoscope.registry.PANELS_MAX'], ['kaleidoscope.W006']),
    ],
)
def test_panels_check_warns_about_unimportable_and_foreign_panels(
    panels: list[str],
    expected: list[str],
) -> None:
    with override_settings(KALEIDOSCOPE_PANELS=panels):
        assert _identifiers(check_panels(None)) == expected


@pytest.mark.parametrize(
    ('ignore_paths', 'expected'),
    [
        (['/admin/'], []),
        (('/admin/', '/static/'), []),
        ([], []),
        ('/admin/', ['kaleidoscope.W007']),
        (None, ['kaleidoscope.W007']),
        (['/admin/', 7], ['kaleidoscope.W007']),
    ],
)
def test_ignore_paths_check_warns_about_anything_but_a_list_of_prefixes(
    ignore_paths: object,
    expected: list[str],
) -> None:
    with override_settings(KALEIDOSCOPE_IGNORE_PATHS=ignore_paths):
        assert _identifiers(check_ignore_paths(None)) == expected


@pytest.mark.parametrize('panels', ['kaleidoscope.panels.timer.TimerPanel', None])
def test_panels_check_warns_once_about_panels_that_are_not_a_list(panels: object) -> None:
    with override_settings(KALEIDOSCOPE_PANELS=panels):
        assert _identifiers(check_panels(None)) == ['kaleidoscope.W008']


def test_subclass_test_refuses_a_base_that_is_not_a_class() -> None:
    with pytest.raises(TypeError, match="base must be a class: 'Panel'"):
        _is_subclass(int, 'Panel')  # ty:ignore[invalid-argument-type]


def test_middleware_test_refuses_a_middleware_class_that_is_not_a_class() -> None:
    with pytest.raises(TypeError, match='middleware_class must be a class: None'):
        _is_middleware_class(None, MIDDLEWARE_GZIP)  # ty:ignore[invalid-argument-type]
