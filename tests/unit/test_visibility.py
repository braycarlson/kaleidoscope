from __future__ import annotations

import pytest

from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from kaleidoscope.visibility import Visibility, _show_default

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.test import RequestFactory


SHOW_CALLBACK_NOT_CALLABLE = 'a constant, not a callable'
SHOW_CALLBACK_NOT_CALLABLE_PATH = 'tests.unit.test_visibility.SHOW_CALLBACK_NOT_CALLABLE'


def _visible_for_staff(request: HttpRequest) -> bool:
    return request.headers.get('X-Role') == 'staff'


async def _visible_for_staff_async(request: HttpRequest) -> bool:
    return request.headers.get('X-Role') == 'staff'


async def _visible_never_async(request: HttpRequest) -> bool:
    _ = request
    message = 'the async show callback is broken'

    raise RuntimeError(message)


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK=None, DEBUG=True, INTERNAL_IPS=['127.0.0.1'])
def test_default_callback_admits_an_internal_address_while_debugging(
    request_factory: RequestFactory,
) -> None:
    visibility = Visibility()
    internal = request_factory.get('/', REMOTE_ADDR='127.0.0.1')
    external = request_factory.get('/', REMOTE_ADDR='10.0.0.9')

    assert visibility.check(internal) is True
    assert visibility.check(external) is False


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK=None, DEBUG=False, INTERNAL_IPS=['127.0.0.1'])
def test_default_callback_refuses_everyone_without_debug(request_factory: RequestFactory) -> None:
    request = request_factory.get('/', REMOTE_ADDR='127.0.0.1')

    assert not Visibility().check(request)


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK='tests.unit.test_visibility._visible_for_staff')
def test_a_custom_sync_callback_decides_in_both_modes(request_factory: RequestFactory) -> None:
    visibility = Visibility()
    staff = request_factory.get('/', headers={'X-Role': 'staff'})
    guest = request_factory.get('/')

    assert visibility.check(staff) is True
    assert visibility.check(guest) is False
    assert async_to_sync(visibility.acheck)(staff) is True
    assert async_to_sync(visibility.acheck)(guest) is False


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK='tests.unit.test_visibility._visible_for_staff_async')
def test_a_custom_async_callback_decides_in_both_modes(request_factory: RequestFactory) -> None:
    visibility = Visibility()
    staff = request_factory.get('/', headers={'X-Role': 'staff'})
    guest = request_factory.get('/')

    assert visibility.check(staff) is True
    assert visibility.check(guest) is False
    assert async_to_sync(visibility.acheck)(staff) is True
    assert async_to_sync(visibility.acheck)(guest) is False


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK='tests.unit.test_visibility._visible_never_async')
def test_a_raising_async_callback_hides_the_toolbar_in_both_modes(
    request_factory: RequestFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    visibility = Visibility()
    request = request_factory.get('/')

    assert visibility.check(request) is False
    assert async_to_sync(visibility.acheck)(request) is False
    assert caplog.text.count('show callback failed') == 2


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK=['tests.unit.test_visibility._visible_for_staff'])
def test_a_show_callback_setting_that_is_not_a_path_is_refused() -> None:
    with pytest.raises(ImproperlyConfigured, match='must be a dotted path, not list'):
        Visibility()


@override_settings(KALEIDOSCOPE_SHOW_CALLBACK=SHOW_CALLBACK_NOT_CALLABLE_PATH)
def test_a_show_callback_that_names_something_uncallable_is_refused() -> None:
    with pytest.raises(ImproperlyConfigured, match='names a str'):
        Visibility()


def test_visibility_refuses_something_that_is_not_a_request() -> None:
    visibility = Visibility()

    with pytest.raises(TypeError, match='needs an HttpRequest, not dict'):
        visibility.check({})  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='needs an HttpRequest, not dict'):
        async_to_sync(visibility.acheck)({})  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='needs an HttpRequest, not NoneType'):
        _show_default(None)  # ty:ignore[invalid-argument-type]
