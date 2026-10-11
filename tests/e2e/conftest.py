from __future__ import annotations

import pytest

from typing import TYPE_CHECKING

from django.core.cache import cache

from kaleidoscope.panels.queries import QueryAction
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.testapp.models import Author, Book
from tests.toolbar import PANEL_IDS_DEFAULT, PANEL_IDS_ISOLATED

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import ConsoleMessage, Error, Page, Playwright
    from pytest_django.live_server_helper import LiveServer


EXPECT_TIMEOUT_MS = 10_000
FAVICON_MISSING = 'favicon.ico'


class ToolbarPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.base_url = base_url
        self.console_expected: list[str] = []
        self.page = page
        self.problems: list[str] = []

    def _console_seen(self, message: ConsoleMessage) -> None:
        if message.type != 'error':
            return

        if FAVICON_MISSING in message.location.get('url', ''):
            return

        if any(expected in message.text for expected in self.console_expected):
            return

        self.problems.append(f'console: {message.text}')

    def _page_failed(self, error: Error) -> None:
        self.problems.append(f'page error: {error}')

    def open(self, path: str) -> None:
        self.page.goto(self.base_url + path)
        self.page.locator('[data-ks="tab"]').wait_for()

    def panel_open(self, panel_id: str) -> None:
        self.page.locator(f'[data-ks-panel="{panel_id}"]').click()
        self.page.locator('[data-ks="panel-title"]').wait_for()

    def strip_open(self) -> None:
        self.page.locator('[data-ks="tab"]').click()
        self.page.locator('[data-ks="strip"]').wait_for()

    def watch(self) -> None:
        self.page.on('console', self._console_seen)
        self.page.on('pageerror', self._page_failed)
        self.page.set_default_timeout(EXPECT_TIMEOUT_MS)


def _reset_paths() -> list[str]:
    actions = (QueryAction.CLEAR, QueryAction.TRACK_AJAX_ON, QueryAction.TRACK_PAGE_ON)
    paths = [f'panels/queries/action/{action}/' for action in actions]

    for panel_id in PANEL_IDS_DEFAULT:
        toggle = 'disable' if panel_id in PANEL_IDS_ISOLATED else 'enable'

        paths.append(f'panels/{panel_id}/{toggle}/')

    return [KALEIDOSCOPE_URL_PREFIX + path for path in paths]


@pytest.fixture(autouse=True, scope='session')
def async_unsafe_allowed() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

        yield


@pytest.fixture
def library_live(transactional_db: None) -> list[Author]:
    _ = transactional_db
    authors = []

    for index in range(4):
        author = Author.objects.create(name=f'writer-{index}')

        Book.objects.create(author=author, title=f'title-{index}')
        authors.append(author)

    return authors


@pytest.fixture
def toolbar(page: Page, live_server: LiveServer) -> Iterator[ToolbarPage]:
    toolbar_page = ToolbarPage(page, live_server.url)

    toolbar_page.watch()

    yield toolbar_page

    assert toolbar_page.problems == []


@pytest.fixture(autouse=True)
def toolbar_state_isolated(live_server: LiveServer, playwright: Playwright) -> None:
    cache.clear()

    request = playwright.request.new_context(base_url=live_server.url)

    try:
        for path in _reset_paths():
            assert request.get(path).ok, path
    finally:
        request.dispose()
