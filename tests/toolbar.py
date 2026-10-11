from __future__ import annotations

import json

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from asgiref.sync import async_to_sync

from kaleidoscope.injector import ResponseInjector
from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.testapp.visibility import HEADER_HIDDEN

if TYPE_CHECKING:
    from django.http import HttpResponse
    from django.test import AsyncClient, Client


HEADERS_AJAX = MappingProxyType({'X-Requested-With': 'XMLHttpRequest'})
HEADERS_HIDDEN = MappingProxyType({HEADER_HIDDEN: '1'})

PANEL_IDS_DEFAULT = (
    'timer',
    'versions',
    'request',
    'queries',
    'templates',
    'cache',
    'staticfiles',
    'signals',
    'settings',
    'memory',
    'profiling',
    'line_profiling',
)

PANEL_IDS_ISOLATED = frozenset({'line_profiling', 'memory', 'profiling'})


def async_get(client: AsyncClient, path: str, **kwargs: Any) -> HttpResponse:
    async def get() -> HttpResponse:
        return await client.get(path, **kwargs)

    return async_to_sync(get)()


def async_post(client: AsyncClient, path: str, **kwargs: Any) -> HttpResponse:
    async def post() -> HttpResponse:
        return await client.post(path, **kwargs)

    return async_to_sync(post)()


def json_read(response: HttpResponse) -> dict:
    return json.loads(response.content)


def panel_action(client: Client, panel_id: str, action: str) -> HttpResponse:
    return client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/{panel_id}/action/{action}/')


def panel_data(client: Client, panel_id: str) -> dict:
    response = client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/{panel_id}/data/')

    if response.status_code != 200:
        message = f'{panel_id} data answered {response.status_code}: {response.content[:200]!r}'
        raise AssertionError(message)

    return json_read(response)


def panel_toggle(client: Client, panel_id: str, *, enabled: bool) -> HttpResponse:
    action = 'enable' if enabled else 'disable'

    return client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/{panel_id}/{action}/')


def panels_listed(client: Client) -> list[dict]:
    response = client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/')

    if response.status_code != 200:
        message = f'panel list answered {response.status_code}'
        raise AssertionError(message)

    return json_read(response)['panels']


def shell_text() -> str:
    return ResponseInjector()._shell_template
