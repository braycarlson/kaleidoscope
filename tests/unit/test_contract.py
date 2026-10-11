from __future__ import annotations

import json

import pytest

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from kaleidoscope.router import KALEIDOSCOPE_URL_PREFIX

from tests.contract import contract_errors, contract_load, schema_errors
from tests.toolbar import (
    HEADERS_AJAX,
    PANEL_IDS_DEFAULT,
    PANEL_IDS_ISOLATED,
    json_read,
    panel_data,
    panel_toggle,
)

if TYPE_CHECKING:
    from django.test import Client

    from tests.testapp.models import Author


def _panel_contract_errors(client: Client, panel_id: str) -> list[str]:
    entry = contract_load()['panels'][panel_id]

    return contract_errors(entry, panel_data(client, panel_id))


def test_the_contract_describes_exactly_the_default_panels() -> None:
    assert sorted(contract_load()['panels']) == sorted(PANEL_IDS_DEFAULT)


@pytest.mark.parametrize(
    ('value', 'errors'),
    [
        ({'a': 1}, []),
        ({'a': 'x'}, ['$.a: expected integer, got str']),
        ({}, ["$: missing 'a'"]),
        ({'a': 1, 'b': 2}, ["$: unexpected 'b'"]),
        ([], ['$: expected object, got list']),
    ],
)
def test_the_schema_checker_reports_each_kind_of_mismatch(value: object, errors: list[str]) -> None:
    schema = {
        'additionalProperties': False,
        'properties': {'a': {'type': 'integer'}},
        'required': ['a'],
        'type': 'object',
    }

    assert schema_errors(value, schema) == errors


@pytest.mark.django_db
@pytest.mark.parametrize('panel_id', PANEL_IDS_DEFAULT)
def test_every_panel_honors_the_contract_before_any_page(
    toolbar_client: Client,
    panel_id: str,
) -> None:
    assert _panel_contract_errors(toolbar_client, panel_id) == []


@pytest.mark.django_db
@pytest.mark.parametrize('panel_id', PANEL_IDS_DEFAULT)
def test_every_panel_honors_the_contract_after_real_traffic(
    toolbar_client: Client,
    library: list[Author],
    panel_id: str,
) -> None:
    _ = library

    toolbar_client.get('/page/')
    toolbar_client.get('/work/?queries=4&distinct=2&templates=2&cache=set:alpha,get:alpha,has:beta')
    toolbar_client.get('/work/?queries=2&kind=json&cache=gos:beta', headers=HEADERS_AJAX)
    toolbar_client.post('/work/?queries=1', {'field': 'value'})

    assert _panel_contract_errors(toolbar_client, panel_id) == []


@pytest.mark.django_db
@pytest.mark.parametrize('panel_id', sorted(PANEL_IDS_ISOLATED))
def test_every_isolated_panel_honors_the_contract_once_it_captured(
    toolbar_client: Client,
    panel_id: str,
) -> None:
    panel_toggle(toolbar_client, panel_id, enabled=True)
    toolbar_client.get('/work/?queries=3&templates=1')

    assert _panel_contract_errors(toolbar_client, panel_id) == []


def test_the_panel_list_honors_the_contract(toolbar_client: Client) -> None:
    response = toolbar_client.get(f'{KALEIDOSCOPE_URL_PREFIX}panels/')

    assert contract_errors(contract_load()['panel_list'], json_read(response)) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    'steps',
    [
        [{'kind': 'key', 'name': 'token'}],
        [{'kind': 'key', 'name': 'authors'}],
        [{'kind': 'key', 'name': 'authors'}, {'kind': 'item', 'index': 0}],
        [{'kind': 'key', 'name': 'missing'}],
    ],
)
def test_template_values_honor_the_contract(
    toolbar_client: Client,
    library: list[Author],
    steps: list[dict],
) -> None:
    _ = library

    toolbar_client.get('/page/')

    query = urlencode({'path': json.dumps(steps), 'template': '0'})

    response = toolbar_client.get(
        f'{KALEIDOSCOPE_URL_PREFIX}panels/templates/action/value/?{query}',
    )

    assert contract_errors(contract_load()['template_value'], json_read(response)) == []


@pytest.mark.django_db
@pytest.mark.parametrize('query_index', [0, 99])
def test_query_plans_honor_the_contract(
    toolbar_client: Client,
    library: list[Author],
    query_index: int,
) -> None:
    _ = library

    toolbar_client.get('/page/')

    request_id = panel_data(toolbar_client, 'queries')['requests'][0]['request_id']
    query = urlencode({'query': query_index, 'request': request_id})

    response = toolbar_client.get(
        f'{KALEIDOSCOPE_URL_PREFIX}panels/queries/action/explain/?{query}',
    )

    assert contract_errors(contract_load()['query_explain'], json_read(response)) == []


@pytest.mark.django_db
def test_signal_sends_honor_the_contract(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?fail=1')

    assert _panel_contract_errors(toolbar_client, 'signals') == []
