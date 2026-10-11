from __future__ import annotations

import pytest

import django.dispatch

from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser, PermissionsMixin
from django.core.cache import cache
from django.db import connections
from django.template import Template
from django.test import AsyncClient, Client, RequestFactory

from kaleidoscope import store
from kaleidoscope.panels import cache as cache_panel
from kaleidoscope.panels import request as request_panel
from kaleidoscope.panels import signals as signals_panel
from kaleidoscope.panels import templates as templates_panel

from tests.testapp.models import Author, Book

if TYPE_CHECKING:
    from collections.abc import Iterator


PERMISSION_METHODS = tuple(request_panel.PERMISSION_METHODS)
SIGNAL_SEND_METHODS = (*signals_panel.SEND_METHODS_ASYNC, *signals_panel.SEND_METHODS_SYNC)

PATCHED_METHODS = (
    (AnonymousUser, PERMISSION_METHODS),
    (PermissionsMixin, PERMISSION_METHODS),
    (django.dispatch.Signal, SIGNAL_SEND_METHODS),
    (Template, ('_render',)),
)

pytest_plugins = ('tests.simulation.pytest_plugin',)


def _execute_wrappers_leaked() -> dict[str, list[object]]:
    leaked = {}

    for alias in connections:
        wrappers = connections[alias].execute_wrappers

        if wrappers:
            leaked[alias] = list(wrappers)

            wrappers.clear()

    return leaked


def _methods_saved() -> list[tuple[type, str, object]]:
    saved = []

    for owner, names in PATCHED_METHODS:
        namespace = vars(owner)

        saved.extend((owner, name, namespace[name]) for name in names if name in namespace)

    return saved


@pytest.fixture(autouse=True)
def toolbar_state_isolated() -> Iterator[None]:
    saved = _methods_saved()

    cache.clear()

    yield

    for owner, name, method in saved:
        setattr(owner, name, method)

    cache_panel._collecting.set(None)
    request_panel._checking.set(None)
    signals_panel._collecting.set(None)
    store._capture_active.set(None)
    templates_panel._collecting.set(None)

    leaked = _execute_wrappers_leaked()

    if leaked:
        pytest.fail(f'execute wrappers leaked past the test: {leaked!r}')


@pytest.fixture
def library(db: None) -> list[Author]:
    _ = db
    authors = []

    for index in range(3):
        author = Author.objects.create(name=f'author-{index}')

        for book_index in range(2):
            Book.objects.create(author=author, title=f'book-{index}-{book_index}')

        authors.append(author)

    return authors


@pytest.fixture
def request_factory() -> RequestFactory:
    return RequestFactory()


@pytest.fixture
def toolbar_client() -> Client:
    return Client(raise_request_exception=False)


@pytest.fixture
def toolbar_client_async() -> AsyncClient:
    return AsyncClient(raise_request_exception=False)
