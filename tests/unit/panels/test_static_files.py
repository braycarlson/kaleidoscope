from __future__ import annotations

import time

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.contrib.staticfiles.finders import get_finder
from django.http import StreamingHttpResponse
from django.test import override_settings

from kaleidoscope.panels import static_files
from kaleidoscope.panels.static_files import (
    StaticFilesPanel,
    _html_text,
    _static_files_listed,
    _static_paths_used,
)

from tests.toolbar import HEADERS_AJAX, panel_data, panels_listed

if TYPE_CHECKING:
    from django.test import Client


STATIC_SCAN_SECONDS_MAX = 1.0
STATIC_URL_RUN_LENGTH = 6_000


@pytest.mark.django_db
def test_static_files_panel_lists_files_the_page_used(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?kind=html')

    data = panel_data(toolbar_client, 'staticfiles')

    assert data['used_files'] == ['testapp/site.css', 'testapp/vendor/static/app.js']
    assert data['used_count'] == 2
    assert 'testapp/site.css' in [entry['path'] for entry in data['all_files']]
    assert data['all_count'] == len(data['all_files'])


@pytest.mark.django_db
@pytest.mark.parametrize('kind', ['json', 'binary', 'text', 'stream'])
def test_static_files_panel_skips_responses_that_are_not_html(
    toolbar_client: Client,
    kind: str,
) -> None:
    toolbar_client.get('/work/?kind=html')
    toolbar_client.get(f'/work/?kind={kind}')

    assert panel_data(toolbar_client, 'staticfiles')['used_files'] == [
        'testapp/site.css',
        'testapp/vendor/static/app.js',
    ]


@pytest.mark.django_db
def test_static_files_panel_ignores_ajax_requests(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/', headers=HEADERS_AJAX)

    assert panel_data(toolbar_client, 'staticfiles') == {}


@pytest.mark.django_db
@override_settings(STATIC_URL=None)
def test_static_files_panel_survives_a_project_without_a_static_url(toolbar_client: Client) -> None:
    response = toolbar_client.get('/work/?kind=html')

    assert response.status_code == 200
    assert panel_data(toolbar_client, 'staticfiles')['used_files'] == []


@pytest.mark.django_db
def test_static_files_summary_counts_used_and_available(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?kind=html')

    data = panel_data(toolbar_client, 'staticfiles')
    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['staticfiles'] == f'2 used, {data["all_count"]} available'


def test_static_files_listing_stops_at_the_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(static_files, 'STATIC_FILES_MAX', 2)

    assert len(_static_files_listed()) <= 2


def test_static_files_listing_skips_hidden_files_like_collectstatic() -> None:
    paths = [entry['path'] for entry in _static_files_listed()]

    assert all(not path.split('/')[-1].startswith('.') for path in paths)


@override_settings(
    STATICFILES_FINDERS=[
        'kaleidoscope.missing.Finder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    ],
)
def test_static_files_listing_survives_a_finder_that_cannot_load(
    caplog: pytest.LogCaptureFixture,
) -> None:
    get_finder.cache_clear()
    paths = [entry['path'] for entry in _static_files_listed()]

    get_finder.cache_clear()

    assert 'testapp/site.css' in paths
    assert 'kaleidoscope.missing.Finder' in caplog.text


def test_static_files_panel_reports_nothing_before_a_page_loads() -> None:
    panel = StaticFilesPanel()

    assert panel.get_data() == {}
    assert panel.get_summary() == '0 available'


def test_static_paths_used_finds_each_distinct_static_path_in_order() -> None:
    content = (
        '<link href="/static/app.css"><script src="/static/app.js?v=1"></script>'
        '<img src="/static/app.css#top"><a href=/static/images/logo.png>logo</a>'
    )

    assert _static_paths_used(content, '/static/') == ['app.css', 'app.js', 'images/logo.png']


def test_static_paths_used_works_with_an_absolute_static_url() -> None:
    content = '<link href="https://cdn.example.com/static/site.css">'

    assert _static_paths_used(content, 'https://cdn.example.com/static/') == ['site.css']


def test_static_paths_used_finds_nothing_without_a_static_url() -> None:
    assert _static_paths_used('<link href="/static/app.css">' * 1000, '') == []


def test_static_paths_used_ignores_a_bare_prefix() -> None:
    assert _static_paths_used('<a href="/static/">x</a>', '/static/') == []


def test_static_paths_used_reads_a_static_url_inside_a_path_as_part_of_that_path() -> None:
    content = '<script src="/static/vendor/static/app.js"></script>'

    assert _static_paths_used(content, '/static/') == ['vendor/static/app.js']


def test_static_paths_used_scans_a_run_of_static_urls_in_linear_time() -> None:
    content = '/static/' * STATIC_URL_RUN_LENGTH
    started = time.perf_counter()
    used = _static_paths_used(content, '/static/')
    elapsed = time.perf_counter() - started

    assert used == [content[len('/static/'):]]
    assert elapsed < STATIC_SCAN_SECONDS_MAX


def test_static_files_listing_is_empty_without_the_staticfiles_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def is_installed(name: str) -> bool:
        _ = name

        return False

    registry = SimpleNamespace(is_installed=is_installed)

    monkeypatch.setattr(static_files, 'apps', registry)

    assert _static_files_listed() == []


@override_settings(
    STATICFILES_FINDERS=[
        'django.contrib.staticfiles.finders.AppDirectoriesFinder',
        'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    ],
)
def test_static_files_listing_stops_asking_finders_once_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_finder.cache_clear()
    monkeypatch.setattr(static_files, 'STATIC_FILES_MAX', 1)

    assert len(_static_files_listed()) == 1


def test_static_paths_used_stops_at_the_search_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(static_files, 'CONTENT_SEARCH_ITERATIONS_MAX', 2)

    content = '<link href="/static/a.css"><link href="/static/b.css"><link href="/static/c.css">'

    assert _static_paths_used(content, '/static/') == ['a.css', 'b.css']


@pytest.mark.django_db
def test_static_files_panel_reads_a_page_whose_charset_cannot_decode(
    toolbar_client: Client,
) -> None:
    toolbar_client.get('/work/?kind=mislabeled')

    assert panel_data(toolbar_client, 'staticfiles')['used_files'] == [
        'testapp/site.css',
        'testapp/vendor/static/app.js',
    ]


def test_static_files_read_no_page_text_from_a_streaming_response() -> None:
    chunks = ['<html></html>']
    response = StreamingHttpResponse(chunks)

    with pytest.raises(TypeError, match='comes from an HttpResponse, not StreamingHttpResponse'):
        _html_text(response)  # ty:ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ('content', 'static_url', 'pattern'),
    [
        (b'<link href="/static/app.css">', '/static/', 'content must be text, not bytes'),
        ('<link href="/static/app.css">', None, 'static_url must be text: None'),
    ],
)
def test_static_paths_used_refuses_content_or_a_static_url_that_is_not_text(
    content: object,
    static_url: object,
    pattern: str,
) -> None:
    with pytest.raises(TypeError, match=pattern):
        _static_paths_used(content, static_url)  # ty:ignore[invalid-argument-type]
