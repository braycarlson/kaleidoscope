from __future__ import annotations

import threading
import weakref

import django.dispatch

from kaleidoscope.constants import RECEIVERS_PER_SIGNAL_MAX
from kaleidoscope.panel import Panel


BUILTIN_SIGNALS = {
    'django.contrib.auth.signals.user_logged_in': 'user_logged_in',
    'django.contrib.auth.signals.user_logged_out': 'user_logged_out',
    'django.contrib.auth.signals.user_login_failed': 'user_login_failed',
    'django.core.signals.got_request_exception': 'got_request_exception',
    'django.core.signals.request_finished': 'request_finished',
    'django.core.signals.request_started': 'request_started',
    'django.core.signals.setting_changed': 'setting_changed',
    'django.db.models.signals.m2m_changed': 'm2m_changed',
    'django.db.models.signals.post_delete': 'post_delete',
    'django.db.models.signals.post_init': 'post_init',
    'django.db.models.signals.post_migrate': 'post_migrate',
    'django.db.models.signals.post_save': 'post_save',
    'django.db.models.signals.pre_delete': 'pre_delete',
    'django.db.models.signals.pre_init': 'pre_init',
    'django.db.models.signals.pre_migrate': 'pre_migrate',
    'django.db.models.signals.pre_save': 'pre_save',
}


class SignalsPanel(Panel):
    panel_id = 'signals'
    title = 'Signals'

    def __init__(self) -> None:
        super().__init__()

        self._data: dict | None = None
        self._lock = threading.Lock()

    def _build_data(self) -> dict:
        signals = []

        sorted_signals = sorted(BUILTIN_SIGNALS.items(), key=lambda entry: entry[1])

        for (module_path, name) in sorted_signals:
            signal = self._get_signal(module_path)

            if not signal:
                continue

            if not isinstance(signal, django.dispatch.Signal):
                continue

            receivers = []

            for receiver_entry in signal.receivers[:RECEIVERS_PER_SIGNAL_MAX]:
                receiver_ref = receiver_entry[1]
                receivers.append(self._get_receiver_info(receiver_ref))

            signals.append({
                'module': module_path,
                'name': name,
                'receiver_count': len(receivers),
                'receivers': receivers,
            })

        return {
            'count': len(signals),
            'signals': signals,
            'total_receivers': sum(
                signal_entry['receiver_count'] for signal_entry in signals
            ),
        }

    def _get_receiver_info(self, receiver: object) -> dict:
        if isinstance(receiver, weakref.ReferenceType):
            receiver = receiver()

            if receiver is None:
                return {
                    'module': '',
                    'name': '(dead reference)',
                    'path': '(dead reference)',
                }

        func = receiver

        if hasattr(receiver, '__wrapped__'):
            func = receiver.__wrapped__

        if hasattr(func, '__self__'):
            module = func.__self__.__class__.__module__
            func_name = getattr(func, '__name__', str(func))
            qualname = f'{func.__self__.__class__.__qualname__}.{func_name}'
        else:
            module = getattr(func, '__module__', '')
            qualname = getattr(func, '__qualname__', getattr(func, '__name__', str(func)))

        return {
            'module': module,
            'name': qualname,
            'path': f'{module}.{qualname}',
        }

    def _get_signal(self, module_path: str) -> object | None:
        parts = module_path.rsplit('.', 1)

        if len(parts) != 2:
            return None

        try:
            module = __import__(parts[0], fromlist=[parts[1]])

            return getattr(module, parts[1], None)
        except (ImportError, AttributeError):
            return None

    def get_data(self) -> dict:
        data = self._build_data()

        with self._lock:
            self._data = data

        return data

    def get_summary(self) -> str:
        with self._lock:
            if self._data:
                return f'{self._data["total_receivers"]} receivers, {self._data["count"]} signals'

        data = self._build_data()

        with self._lock:
            self._data = data

        return f'{data["total_receivers"]} receivers, {data["count"]} signals'
