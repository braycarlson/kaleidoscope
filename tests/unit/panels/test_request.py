from __future__ import annotations

import contextvars
import functools
import uuid

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser, PermissionsMixin, User
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http import HttpResponse
from django.test.client import MULTIPART_CONTENT, encode_multipart

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panels import request as request_panel
from kaleidoscope.panels.request import (
    PARTIAL_DEPTH_MAX,
    PERMISSION_METHODS,
    RequestPanel,
    _check_wrapper_build,
    _target_label,
    _url_path_shortened,
)
from kaleidoscope.patch import is_patched

from tests.testapp.models import Author
from tests.toolbar import HEADERS_AJAX, panel_data, panels_listed

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest
    from django.test import Client, RequestFactory


def _view_target(request: HttpRequest) -> HttpResponse:
    _ = request

    return HttpResponse('target')


def _view_described(request: HttpRequest, func: object) -> dict:
    request.resolver_match = SimpleNamespace(
        args=(),
        func=func,
        kwargs={},
        route='target/',
        url_name='target',
        view_name='target',
    )

    panel = RequestPanel()
    response = HttpResponse('ok')
    context = KaleidoscopeContext()

    panel.process_response(request, response, context)

    return panel.get_data()['view']


@pytest.mark.django_db
def test_request_panel_describes_the_last_page_and_its_view(toolbar_client: Client) -> None:
    toolbar_client.get('/work/?queries=0&token=described', headers={'X-Custom': 'value'})

    data = panel_data(toolbar_client, 'request')

    assert data['method'] == 'GET'
    assert data['path'].startswith('/work/?')
    assert data['status_code'] == 200
    assert data['get']['token'] == ['described']
    assert data['headers']['X-Custom'] == 'value'
    assert data['response_headers']['Content-Type'] == 'text/html; charset=utf-8'
    assert data['view']['func'] == 'tests.testapp.views.work_view'
    assert data['view']['url_name'] == 'work'
    assert data['view']['route'] == 'work/'


@pytest.mark.django_db
def test_request_panel_ignores_ajax_requests(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')
    toolbar_client.get('/work/', headers=HEADERS_AJAX)

    assert panel_data(toolbar_client, 'request')['path'] == '/plain/'


@pytest.mark.django_db
def test_request_panel_lets_a_view_read_the_body_of_a_multipart_post(
    toolbar_client: Client,
) -> None:
    fields = {'name': 'value', 'other': 'field'}
    response = toolbar_client.post('/body/', fields)

    assert response.status_code == 200
    assert int(response.content) > 0

    data = panel_data(toolbar_client, 'request')

    assert data['status_code'] == 200
    assert data['post'] == {'name': ['value'], 'other': ['field']}


@pytest.mark.django_db
def test_request_panel_records_form_fields_the_view_parsed(toolbar_client: Client) -> None:
    fields = {'name': 'value'}

    toolbar_client.post('/work/', fields)

    data = panel_data(toolbar_client, 'request')

    assert data['method'] == 'POST'
    assert data['post'] == {'name': ['value']}


@pytest.mark.django_db
def test_request_panel_survives_a_multipart_body_without_a_boundary(
    toolbar_client: Client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = encode_multipart('boundary', {'name': 'value'})
    response = toolbar_client.post('/plain/', body, content_type='multipart/form-data')

    assert response.status_code == 200
    assert panel_data(toolbar_client, 'request')['post'] == {}
    assert 'could not read the POST data' in caplog.text


@pytest.mark.django_db
def test_request_panel_reads_a_well_formed_multipart_body(toolbar_client: Client) -> None:
    body = encode_multipart('boundary', {'name': 'value'})
    content_type = MULTIPART_CONTENT.replace('BoUnDaRyStRiNg', 'boundary')
    response = toolbar_client.post('/plain/', body, content_type=content_type)

    assert response.status_code == 200
    assert panel_data(toolbar_client, 'request')['post'] == {'name': ['value']}


@pytest.mark.django_db
def test_request_panel_shows_view_arguments_json_cannot_hold(toolbar_client: Client) -> None:
    toolbar_client.get('/color/crimson/')

    data = panel_data(toolbar_client, 'request')

    assert data['view']['kwargs'] == {'color': "Color(name='crimson')"}


@pytest.mark.django_db
def test_request_panel_keeps_view_arguments_json_can_hold(toolbar_client: Client) -> None:
    identifier = uuid.uuid4()

    toolbar_client.get(f'/uuid/{identifier}/')

    data = panel_data(toolbar_client, 'request')

    assert data['view']['kwargs'] == {'identifier': str(identifier)}


@pytest.mark.django_db
def test_request_panel_summary_names_method_status_and_path(toolbar_client: Client) -> None:
    toolbar_client.get('/plain/')

    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['request'] == 'GET 200 /plain/'


def test_request_panel_summary_is_empty_before_any_request(toolbar_client: Client) -> None:
    summaries = {panel['id']: panel['summary'] for panel in panels_listed(toolbar_client)}

    assert summaries['request'] == ''


def test_url_path_shortened_keeps_the_path_within_its_length() -> None:
    assert _url_path_shortened('/plain/?token=abc', 20) == '/plain/'
    assert _url_path_shortened('/a/very/long/path/that/keeps/going/', 20) == '/a/very/long/path...'


def test_request_panel_names_the_view_a_partial_wraps(request_factory: RequestFactory) -> None:
    func = functools.partial(functools.partial(_view_target))
    view = _view_described(request_factory.get('/target/'), func)

    assert view['func'] == 'tests.unit.panels.test_request._view_target'


def test_request_panel_stops_unwrapping_partials_at_the_depth_maximum(
    request_factory: RequestFactory,
) -> None:
    func: object = _view_target

    for level in range(PARTIAL_DEPTH_MAX + 1):
        func = functools.partial(func)
        func.level = level

    view = _view_described(request_factory.get('/target/'), func)

    assert view['func'] == 'functools.partial'


@pytest.mark.parametrize(
    ('url', 'length_max', 'error', 'pattern'),
    [
        (7, 20, TypeError, 'url must be text: 7'),
        ('/plain/', 2, ValueError, 'length_max must leave room for an ellipsis: 2'),
    ],
)
def test_url_path_shortened_refuses_a_url_or_a_length_it_cannot_use(
    url: object,
    length_max: int,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        _url_path_shortened(url, length_max)  # ty:ignore[invalid-argument-type]


class _SessionUnreadable:
    accessed = False
    modified = False

    def items(self) -> list:
        message = 'the session store is down'
        raise RuntimeError(message)


class _UserUnreadable:
    pk = None

    def __str__(self) -> str:
        message = 'the user cannot be named'
        raise RuntimeError(message)


def _checks_collected(
    request_factory: RequestFactory,
    run: Callable[[], object],
    *,
    is_ajax: bool = False,
) -> RequestPanel:
    panel = RequestPanel()
    request = request_factory.get('/')
    context = KaleidoscopeContext(is_ajax=is_ajax)

    panel.install()
    panel.process_request(request, context)

    try:
        run()
    finally:
        panel.process_response(request, HttpResponse(), context)

    return panel


def _described(request: HttpRequest) -> dict:
    panel = RequestPanel()

    panel.process_response(request, HttpResponse(), KaleidoscopeContext())

    return panel.get_data()


def test_request_panel_shows_the_session_and_leaves_it_as_it_found_it(
    request_factory: RequestFactory,
) -> None:
    session = SessionStore()
    session['cart'] = [1, 2]
    session.accessed = False
    request = request_factory.get('/')
    request.session = session

    described = _described(request)['session']

    assert described['items'] == {'cart': [1, 2]}
    assert described['accessed'] is False
    assert described['modified'] is True
    assert described['backend'] == 'django.contrib.sessions.backends.signed_cookies.SessionStore'
    assert described['expire_at_browser_close'] is False
    assert described['expiry_age'] > 0
    assert session.accessed is False


def test_request_panel_reports_a_session_it_cannot_read(
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = request_factory.get('/')
    request.session = _SessionUnreadable()

    described = _described(request)['session']

    assert described['items'] == {}
    assert described['expiry_age'] == 0
    assert 'could not read the session' in caplog.text


@pytest.mark.django_db
def test_request_panel_has_no_session_or_user_without_their_middleware(
    toolbar_client: Client,
) -> None:
    toolbar_client.get('/plain/')

    data = panel_data(toolbar_client, 'request')

    assert data['session'] is None
    assert data['user'] is None
    assert data['permissions'] == []


@pytest.mark.django_db
def test_request_panel_describes_a_signed_in_user_and_an_anonymous_one(
    request_factory: RequestFactory,
) -> None:
    reader = User.objects.create_user('reader')
    signed_in = request_factory.get('/')
    signed_in.user = reader
    anonymous = request_factory.get('/')
    anonymous.user = AnonymousUser()

    assert _described(signed_in)['user'] == {
        'active': True,
        'authenticated': True,
        'id': str(reader.pk),
        'name': 'reader',
        'staff': False,
        'superuser': False,
    }

    assert _described(anonymous)['user'] == {
        'active': False,
        'authenticated': False,
        'id': '',
        'name': 'AnonymousUser',
        'staff': False,
        'superuser': False,
    }


def test_request_panel_reports_a_user_it_cannot_read(
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = request_factory.get('/')
    request.user = _UserUnreadable()

    assert _described(request)['user'] is None
    assert 'could not read the user' in caplog.text


@pytest.mark.django_db
def test_request_panel_records_each_permission_check_with_its_result(
    request_factory: RequestFactory,
) -> None:
    reader = User.objects.create_user('reader')
    admin = User.objects.create_superuser('admin', password='unused')
    author = Author.objects.create(name='checked')

    def checks_run() -> None:
        reader.has_perm('testapp.view_author')
        AnonymousUser().has_perm('testapp.view_author')
        reader.has_perm('testapp.change_author', author)
        admin.has_perm('testapp.delete_author')
        admin.has_module_perms('testapp')
        reader.has_perms(['testapp.add_author'])

    panel = _checks_collected(request_factory, checks_run)

    expected = [
        ('permission', 'testapp.view_author', '', False, False, 2),
        ('permission', 'testapp.change_author', f'Author {author.pk}', False, False, 1),
        ('permission', 'testapp.delete_author', '', True, True, 1),
        ('module', 'testapp', '', True, True, 1),
        ('permission', 'testapp.add_author', '', False, False, 1),
    ]

    checks = [
        (
            check['kind'],
            check['name'],
            check['target'],
            check['result'],
            check['superuser'],
            check['count'],
        )
        for check in panel.get_data()['permissions']
    ]

    assert checks == expected


@pytest.mark.django_db
def test_request_panel_records_a_check_whose_arguments_are_named(
    request_factory: RequestFactory,
) -> None:
    reader = User.objects.create_user('reader')
    admin = User.objects.create_superuser('admin', password='unused')
    author = Author.objects.create(name='checked')

    def checks_run() -> None:
        reader.has_perm(perm='testapp.change_author', obj=author)
        admin.has_module_perms(app_label='testapp')
        AnonymousUser().has_module_perms(module='testapp')

    panel = _checks_collected(request_factory, checks_run)
    checks = [(check['name'], check['target']) for check in panel.get_data()['permissions']]

    expected = [
        ('testapp.change_author', f'Author {author.pk}'),
        ('testapp', ''),
        ('testapp', ''),
    ]

    assert checks == expected


def test_request_panel_closes_the_checks_of_an_ajax_request(
    request_factory: RequestFactory,
) -> None:
    logs: list[object] = []

    def checks_run() -> None:
        logs.append(request_panel._checking.get())

        AnonymousUser().has_perm('testapp.view_author')

    panel = _checks_collected(request_factory, checks_run, is_ajax=True)

    assert logs[0].closed is True
    assert panel.get_data() == {}


def test_a_permission_check_from_work_that_outlived_its_response_is_not_recorded(
    request_factory: RequestFactory,
) -> None:
    panel = RequestPanel()
    request = request_factory.get('/')
    context = KaleidoscopeContext()

    panel.install()
    panel.process_request(request, context)

    lingering = contextvars.copy_context()

    panel.process_response(request, HttpResponse(), context)
    lingering.run(AnonymousUser().has_perm, 'testapp.view_author')

    assert panel.get_data()['permissions'] == []


def test_permission_checks_outside_a_collecting_request_pass_straight_through() -> None:
    RequestPanel().install()

    assert AnonymousUser().has_perm('testapp.view_author') is False
    assert request_panel._checking.get(None) is None


def test_permission_checks_past_the_maximum_are_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    monkeypatch.setattr(request_panel, 'PERMISSION_CHECKS_MAX', 1)

    def checks_run() -> None:
        AnonymousUser().has_perm('testapp.view_author')
        AnonymousUser().has_perm('testapp.view_author')

    checks = _checks_collected(request_factory, checks_run).get_data()['permissions']

    assert [check['count'] for check in checks] == [1]


def test_a_new_kind_of_check_past_the_group_maximum_is_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
) -> None:
    monkeypatch.setattr(request_panel, 'PERMISSION_GROUPS_MAX', 1)

    def checks_run() -> None:
        AnonymousUser().has_perm('testapp.view_author')
        AnonymousUser().has_perm('testapp.change_author')

    checks = _checks_collected(request_factory, checks_run).get_data()['permissions']

    assert [check['name'] for check in checks] == ['testapp.view_author']


def test_a_check_that_cannot_be_recorded_is_logged_and_still_answered(
    monkeypatch: pytest.MonkeyPatch,
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    answers: list[object] = []

    def record_broken(log: object, **keywords: object) -> None:
        _ = log
        _ = keywords
        message = 'recording is broken'

        raise RuntimeError(message)

    monkeypatch.setattr(request_panel, '_check_record', record_broken)

    _checks_collected(request_factory, lambda: answers.append(AnonymousUser().has_perm('x.y')))

    assert answers == [False]
    assert 'could not record a permission check' in caplog.text


def test_install_wraps_each_permission_method_once_and_uninstall_restores_them() -> None:
    owners = (AnonymousUser, PermissionsMixin)
    keys = [(owner, name) for owner in owners for name in PERMISSION_METHODS]
    originals = {key: vars(key[0])[key[1]] for key in keys}
    first = RequestPanel()
    second = RequestPanel()

    first.install()
    second.install()

    wrapped = {key: vars(key[0])[key[1]] for key in originals}

    second.uninstall()

    assert all(is_patched(method) for method in wrapped.values())
    assert {key: method.__wrapped__ for key, method in wrapped.items()} == originals
    assert {key: vars(key[0])[key[1]] for key in originals} == originals


def test_install_patches_nothing_without_the_auth_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_panel.apps, 'is_installed', lambda _label: False)

    original = vars(PermissionsMixin)['has_perm']
    panel = RequestPanel()

    panel.install()
    panel.uninstall()

    assert vars(PermissionsMixin)['has_perm'] is original


def test_permission_wrappers_refuse_something_that_cannot_check() -> None:
    with pytest.raises(TypeError, match='original must be callable, not NoneType'):
        _check_wrapper_build(None, kind='permission')  # ty:ignore[invalid-argument-type]


def test_a_check_target_is_named_by_its_type_and_its_key() -> None:
    assert _target_label(None) == ''
    assert _target_label(object()) == 'object'
    assert _target_label(Author()) == 'Author'
    assert _target_label(SimpleNamespace(pk=7)) == 'SimpleNamespace 7'
