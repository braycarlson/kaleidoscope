from __future__ import annotations

import contextvars
import functools
import gc
import sys

import pytest

import django.dispatch

from types import ModuleType
from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.db.models.signals import post_save, pre_save
from django.http import HttpResponse
from django.test import RequestFactory

from kaleidoscope.context import KaleidoscopeContext
from kaleidoscope.panels import signals as signals_panel
from kaleidoscope.panels.signals import (
    BUILTIN_SIGNALS,
    SEND_METHODS_ASYNC,
    SEND_METHODS_SYNC,
    SIGNAL_NAME_UNKNOWN,
    SignalsPanel,
    _send_async_wrapper_build,
    _send_wrapper_build,
    _sender_label,
    _signal_candidates,
    _signal_described,
    _signal_path_chosen,
)
from kaleidoscope.patch import is_patched

from tests.testapp.models import Author
from tests.testapp.signals import shelved, unshelved
from tests.testapp.work import spin_for_profile
from tests.toolbar import panel_data

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from django.test import Client


SEND_METHODS = tuple(
    name
    for name in (*SEND_METHODS_ASYNC, *SEND_METHODS_SYNC)
    if hasattr(django.dispatch.Signal, name)
)
SENDS_ASYNC_MISSING = not hasattr(django.dispatch.Signal, 'asend')
SHELVED_PATH = 'tests.testapp.signals.shelved'


class _Listener:
    def received(self, sender: object, **kwargs: object) -> None:
        _ = sender
        _ = kwargs


class _ModuleClosed(ModuleType):
    @property
    def __dict__(self) -> dict:  # ty:ignore[invalid-method-override]
        message = 'the module namespace is closed'
        raise TypeError(message)


async def _receiver_awaited(sender: object, **kwargs: object) -> None:
    _ = sender
    _ = kwargs


def _receiver_failing(sender: object, **kwargs: object) -> None:
    _ = sender
    _ = kwargs
    message = 'the receiver failed'

    raise RuntimeError(message)


def _receiver_function(sender: object, **kwargs: object) -> None:
    _ = sender
    _ = kwargs


def _receiver_relaying(sender: object, **kwargs: object) -> None:
    _ = kwargs

    unshelved.send(sender=sender)


def _receiver_slow(sender: object, **kwargs: object) -> None:
    _ = sender
    _ = kwargs

    spin_for_profile(2)


def _record_broken(log: object, **keywords: object) -> None:
    _ = log
    _ = keywords
    message = 'recording is broken'

    raise RuntimeError(message)


def _receivers_of(name: str) -> list[dict]:
    signals = SignalsPanel().get_data()['signals']

    return next(signal['receivers'] for signal in signals if signal['name'] == name)


def _sends_collected(
    panel: SignalsPanel,
    run: Callable[[], object],
    *,
    is_ajax: bool = False,
) -> None:
    request = RequestFactory().get('/')
    context = KaleidoscopeContext(is_ajax=is_ajax)

    panel.install()
    panel.process_request(request, context)

    try:
        run()
    finally:
        panel.process_response(request, HttpResponse(), context)


def _sends_of(panel: SignalsPanel) -> list[dict]:
    return panel.get_data()['sends']


def _wrapped(target: Callable[..., None]) -> Callable[..., None]:
    @functools.wraps(target)
    def wrapper(sender: object, **kwargs: object) -> None:
        target(sender, **kwargs)

    return wrapper


@pytest.fixture
def listener() -> Iterator[_Listener]:
    instance = _Listener()

    post_save.connect(instance.received, dispatch_uid='kaleidoscope-listener')

    yield instance

    post_save.disconnect(dispatch_uid='kaleidoscope-listener')


def test_signals_list_each_builtin_signal_and_each_one_a_module_defines() -> None:
    data = SignalsPanel().get_data()
    modules = [signal['module'] for signal in data['signals']]
    names = [signal['name'] for signal in data['signals']]

    assert set(BUILTIN_SIGNALS) <= set(modules)
    assert SHELVED_PATH in modules
    assert names == sorted(names)
    assert data['count'] == len(names)
    assert data['total_receivers'] == sum(signal['receiver_count'] for signal in data['signals'])


def test_signals_name_a_function_receiver_by_its_path() -> None:
    pre_save.connect(_receiver_function, dispatch_uid='kaleidoscope-function')

    try:
        receivers = _receivers_of('pre_save')
    finally:
        pre_save.disconnect(dispatch_uid='kaleidoscope-function')

    paths = [receiver['path'] for receiver in receivers]

    assert f'{__name__}._receiver_function' in paths


def test_signals_name_a_bound_method_receiver_by_its_class(listener: _Listener) -> None:
    _ = listener
    paths = [receiver['path'] for receiver in _receivers_of('post_save')]

    assert f'{__name__}._Listener.received' in paths


def test_signals_name_a_wrapped_receiver_by_the_function_it_wraps() -> None:
    wrapped = _wrapped(_receiver_function)

    pre_save.connect(wrapped, dispatch_uid='kaleidoscope-wrapped', weak=False)

    try:
        receivers = _receivers_of('pre_save')
    finally:
        pre_save.disconnect(dispatch_uid='kaleidoscope-wrapped')

    assert f'{__name__}._receiver_function' in [receiver['path'] for receiver in receivers]


def test_signals_mark_a_receiver_that_was_garbage_collected() -> None:
    instance = _Listener()

    post_save.connect(instance.received, dispatch_uid='kaleidoscope-dead')

    try:
        receivers_before = len(_receivers_of('post_save'))

        del instance
        gc.collect()
        receivers = _receivers_of('post_save')
    finally:
        post_save.disconnect(dispatch_uid='kaleidoscope-dead')

    assert len(receivers) <= receivers_before


def test_signals_summary_counts_receivers_and_signals() -> None:
    panel = SignalsPanel()
    data = panel.get_data()

    assert panel.get_summary() == f'{data["total_receivers"]} receivers, {data["count"]} signals'
    assert SignalsPanel().get_summary() == panel.get_summary()


def test_signals_summary_counts_the_sends_of_the_last_page() -> None:
    panel = SignalsPanel()

    _sends_collected(panel, lambda: shelved.send(sender=Author))

    assert panel.get_summary().startswith('1 sends, ')
    assert panel.get_summary().endswith(' ms')


def test_signals_skip_a_builtin_path_that_names_no_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    builtin = {
        'django.conf.settings': 'not_a_signal',
        'django.core.signals.request_started': 'request_started',
        'kaleidoscope.missing.signal': 'missing',
    }

    monkeypatch.setattr(signals_panel, 'BUILTIN_SIGNALS', builtin)

    modules = [signal['module'] for signal in SignalsPanel().get_data()['signals']]

    assert 'django.core.signals.request_started' in modules
    assert 'django.conf.settings' not in modules
    assert 'kaleidoscope.missing.signal' not in modules


@pytest.mark.parametrize(
    ('path', 'error', 'pattern'),
    [
        (7, TypeError, 'a signal path must be text: 7'),
        ('', ValueError, 'a signal needs a path'),
    ],
)
def test_signals_refuse_a_path_that_is_no_text_or_empty(
    path: object,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        _signal_described(shelved, path)  # ty:ignore[invalid-argument-type]


def test_a_send_is_recorded_with_its_sender_receivers_site_and_time() -> None:
    panel = SignalsPanel()

    shelved.connect(_receiver_function, dispatch_uid='kaleidoscope-shelved')

    try:
        _sends_collected(panel, lambda: [shelved.send(sender=Author) for _ in range(3)])
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-shelved')

    data = panel.get_data()
    send = data['sends'][0]

    assert data['send_count'] == 3
    assert send['count'] == 3
    assert send['name'] == 'shelved'
    assert send['module'] == SHELVED_PATH
    assert send['sender'] == 'tests.testapp.models.Author'
    assert send['receivers'] == [f'{__name__}._receiver_function']
    assert send['errors'] == 0
    assert send['site']['file'] == __file__
    assert send['duration_ms'] >= 0.0


def test_a_robust_send_counts_each_receiver_that_failed() -> None:
    panel = SignalsPanel()

    shelved.connect(_receiver_failing, dispatch_uid='kaleidoscope-failing')

    try:
        _sends_collected(panel, lambda: shelved.send_robust(sender=None))
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-failing')

    send = _sends_of(panel)[0]

    assert send['errors'] == 1
    assert send['sender'] == ''


def test_a_send_whose_receiver_raises_is_recorded_as_failed_and_still_raises() -> None:
    panel = SignalsPanel()

    def run() -> None:
        with pytest.raises(RuntimeError, match='the receiver failed'):
            shelved.send(sender=Author)

    shelved.connect(_receiver_failing, dispatch_uid='kaleidoscope-failing')

    try:
        _sends_collected(panel, run)
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-failing')

    send = _sends_of(panel)[0]

    assert send['errors'] == 1
    assert send['receivers'] == []
    assert signals_panel._depth.get() == 0


@pytest.mark.skipif(SENDS_ASYNC_MISSING, reason='Signal.asend arrives in Django 5.0')
def test_async_sends_are_recorded_like_the_others() -> None:
    panel = SignalsPanel()

    async def sends_awaited() -> None:
        await shelved.asend(sender=Author)
        await shelved.asend_robust(sender=Author)

    shelved.connect(_receiver_awaited, dispatch_uid='kaleidoscope-awaited')

    try:
        _sends_collected(panel, async_to_sync(sends_awaited))
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-awaited')

    send = _sends_of(panel)[0]

    assert send['count'] == 2
    assert send['receivers'] == [f'{__name__}._receiver_awaited']


@pytest.mark.skipif(SENDS_ASYNC_MISSING, reason='Signal.asend arrives in Django 5.0')
def test_sends_outside_a_collecting_request_pass_straight_through() -> None:
    async def send_awaited() -> list:
        return await shelved.asend(sender=Author)

    SignalsPanel().install()

    responses = shelved.send(sender=Author)
    responses_awaited = async_to_sync(send_awaited)()

    assert responses == []
    assert responses_awaited == []
    assert signals_panel._collecting.get(None) is None


def test_a_send_inside_a_receiver_counts_once_toward_the_total() -> None:
    panel = SignalsPanel()

    shelved.connect(_receiver_relaying, dispatch_uid='kaleidoscope-relaying')
    unshelved.connect(_receiver_slow, dispatch_uid='kaleidoscope-slow')

    try:
        _sends_collected(panel, lambda: shelved.send(sender=Author))
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-relaying')
        unshelved.disconnect(dispatch_uid='kaleidoscope-slow')

    data = panel.get_data()
    durations = {send['name']: send['duration_ms'] for send in data['sends']}

    assert durations['unshelved'] > 0.0
    assert data['send_time'] == durations['shelved']


def test_ajax_sends_join_the_page_and_a_page_starts_over() -> None:
    panel = SignalsPanel()

    def sends_both() -> None:
        shelved.send(sender=Author)
        unshelved.send(sender=None)

    _sends_collected(panel, lambda: shelved.send(sender=Author))
    _sends_collected(panel, sends_both, is_ajax=True)

    merged = {send['name']: send['count'] for send in _sends_of(panel)}

    _sends_collected(panel, lambda: unshelved.send(sender=None))

    restarted = {send['name']: send['count'] for send in _sends_of(panel)}

    assert merged == {'shelved': 2, 'unshelved': 1}
    assert restarted == {'unshelved': 1}


def test_sends_past_the_per_request_maximum_are_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(signals_panel, 'SIGNAL_SENDS_MAX', 2)

    panel = SignalsPanel()

    _sends_collected(panel, lambda: [shelved.send(sender=Author) for _ in range(5)])

    assert panel.get_data()['send_count'] == 2


def test_a_new_kind_of_send_past_the_group_maximum_is_not_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(signals_panel, 'SEND_GROUPS_MAX', 1)

    panel = SignalsPanel()

    def sends_both() -> None:
        shelved.send(sender=Author)
        unshelved.send(sender=None)

    _sends_collected(panel, sends_both)
    _sends_collected(panel, lambda: unshelved.send(sender=Author), is_ajax=True)

    assert [send['name'] for send in _sends_of(panel)] == ['shelved']


def test_install_wraps_each_send_method_once_and_uninstall_restores_them() -> None:
    namespace = vars(django.dispatch.Signal)
    originals = {name: namespace[name] for name in SEND_METHODS}
    first = SignalsPanel()
    second = SignalsPanel()

    first.install()
    second.install()

    wrapped = {name: namespace[name] for name in SEND_METHODS}

    second.uninstall()

    assert all(is_patched(method) for method in wrapped.values())
    assert {name: method.__wrapped__ for name, method in wrapped.items()} == originals
    assert {name: namespace[name] for name in SEND_METHODS} == originals


def test_install_skips_a_send_method_this_django_lacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(django.dispatch.Signal, 'send_robust')

    SignalsPanel().install()

    assert 'send_robust' not in vars(django.dispatch.Signal)
    assert is_patched(vars(django.dispatch.Signal)['send'])


def test_send_wrappers_refuse_something_that_cannot_send() -> None:
    with pytest.raises(TypeError, match='original must be callable, not NoneType'):
        _send_wrapper_build(None, robust=False)  # ty:ignore[invalid-argument-type]

    with pytest.raises(TypeError, match='original must be callable, not NoneType'):
        _send_async_wrapper_build(None, robust=False)  # ty:ignore[invalid-argument-type]


def test_a_send_that_cannot_be_recorded_is_logged_and_still_delivered(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    senders: list[object] = []

    def receiver(sender: object, **kwargs: object) -> None:
        _ = kwargs

        senders.append(sender)

    monkeypatch.setattr(signals_panel, '_send_record', _record_broken)
    shelved.connect(receiver, weak=False, dispatch_uid='kaleidoscope-received')

    try:
        _sends_collected(SignalsPanel(), lambda: shelved.send(sender=Author))
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-received')

    assert senders == [Author]
    assert 'could not record a signal send' in caplog.text


@pytest.mark.skipif(SENDS_ASYNC_MISSING, reason='Signal.asend arrives in Django 5.0')
def test_an_async_send_that_cannot_be_recorded_is_logged_and_still_delivered(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def send_awaited() -> list:
        return await shelved.asend(sender=Author)

    monkeypatch.setattr(signals_panel, '_send_record', _record_broken)
    shelved.connect(_receiver_awaited, dispatch_uid='kaleidoscope-awaited')

    responses: list = []

    try:
        _sends_collected(SignalsPanel(), lambda: responses.extend(async_to_sync(send_awaited)()))
    finally:
        shelved.disconnect(dispatch_uid='kaleidoscope-awaited')

    assert [receiver for receiver, _response in responses] == [_receiver_awaited]
    assert 'could not record a signal send' in caplog.text


@pytest.mark.parametrize(
    ('sender', 'label'),
    [
        (None, ''),
        (Author, 'tests.testapp.models.Author'),
        (7, 'int'),
    ],
)
def test_a_sender_is_named_by_its_class_path_or_its_type(sender: object, label: str) -> None:
    assert _sender_label(sender) == label


def test_a_send_of_a_signal_no_module_holds_is_named_unknown() -> None:
    panel = SignalsPanel()
    signal_local = django.dispatch.Signal()

    _sends_collected(panel, lambda: signal_local.send(sender=None))

    send = _sends_of(panel)[0]

    assert send['name'] == SIGNAL_NAME_UNKNOWN
    assert send['module'] == ''


def test_a_signal_found_in_several_modules_is_named_by_the_module_that_defines_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / 'zz_defining.py'
    source.write_text('relayed = Signal()\n', encoding='utf-8')

    defining = ModuleType('zz_defining')
    defining.__file__ = str(source)

    monkeypatch.setitem(sys.modules, 'zz_defining', defining)
    monkeypatch.setitem(sys.modules, 'aa_importing', ModuleType('aa_importing'))

    found = ['aa_importing.relayed', 'zz_defining.relayed']

    assert _signal_path_chosen(found) == 'zz_defining.relayed'


def test_a_signal_no_module_visibly_defines_is_named_by_its_likeliest_path() -> None:
    alone = ['app.views.relayed']
    conventional = ['app.views.relayed', 'app.signals.relayed']
    shallower = ['app.views.relayed', 'app.relayed']

    assert _signal_path_chosen(alone) == 'app.views.relayed'
    assert _signal_path_chosen(conventional) == 'app.signals.relayed'
    assert _signal_path_chosen(shallower) == 'app.relayed'


def test_signal_discovery_skips_entries_that_are_no_readable_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, 'kaleidoscope_not_a_module', object())
    monkeypatch.setitem(sys.modules, 'kaleidoscope_closed', _ModuleClosed('kaleidoscope_closed'))

    paths = [path for found in _signal_candidates().values() for path in found]

    assert not any(path.startswith('kaleidoscope_') for path in paths)


def test_signal_discovery_stops_at_the_attribute_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signals_panel, 'SIGNAL_ATTRIBUTES_MAX', 0)

    assert _signal_candidates() == {}


def test_a_send_from_work_that_outlived_its_response_is_not_recorded() -> None:
    panel = SignalsPanel()
    request = RequestFactory().get('/')
    context = KaleidoscopeContext(is_ajax=True)

    panel.install()
    panel.process_request(request, context)

    lingering = contextvars.copy_context()

    panel.process_response(request, HttpResponse(), context)
    lingering.run(shelved.send, sender=Author)

    assert panel.get_data()['send_count'] == 0


def test_signals_panel_keeps_its_sends_when_no_collector_opened(
    request_factory: RequestFactory,
) -> None:
    panel = SignalsPanel()

    _sends_collected(panel, lambda: shelved.send(sender=Author))
    panel.process_response(request_factory.get('/'), HttpResponse(), KaleidoscopeContext())

    assert panel.get_data()['send_count'] == 1


def test_signals_panel_refuses_a_context_that_is_not_one(request_factory: RequestFactory) -> None:
    panel = SignalsPanel()
    request = request_factory.get('/')

    with pytest.raises(TypeError, match='needs a KaleidoscopeContext, not NoneType'):
        panel.process_response(request, HttpResponse(), None)  # ty:ignore[invalid-argument-type]


@pytest.mark.django_db
def test_signals_panel_records_the_exception_signal_of_a_failing_page(
    toolbar_client: Client,
) -> None:
    toolbar_client.get('/work/?fail=1')

    names = [send['name'] for send in panel_data(toolbar_client, 'signals')['sends']]

    assert 'got_request_exception' in names
