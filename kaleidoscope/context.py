from __future__ import annotations

import time
import uuid

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kaleidoscope.panel import Panel


def _request_id() -> str:
    return uuid.uuid4().hex


@dataclass
class KaleidoscopeContext:
    asgi: bool = False
    is_ajax: bool = False
    panels: list[Panel] = field(default_factory=list)
    request_id: str = field(default_factory=_request_id)
    started_ns: int = field(default_factory=time.perf_counter_ns)
    state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.asgi, bool):
            message = f'asgi must be a bool: {self.asgi!r}'
            raise TypeError(message)

        if not isinstance(self.is_ajax, bool):
            message = f'is_ajax must be a bool: {self.is_ajax!r}'
            raise TypeError(message)

        if not isinstance(self.panels, list):
            message = f'panels must be a list: {self.panels!r}'
            raise TypeError(message)

        if not isinstance(self.request_id, str):
            message = f'request_id must be text: {self.request_id!r}'
            raise TypeError(message)

        if not self.request_id:
            message = 'request_id must not be empty'
            raise ValueError(message)

        if isinstance(self.started_ns, bool):
            message = f'started_ns must be an integer, not a bool: {self.started_ns!r}'
            raise TypeError(message)

        if not isinstance(self.started_ns, int):
            message = f'started_ns must be an integer: {self.started_ns!r}'
            raise TypeError(message)

        if not isinstance(self.state, dict):
            message = f'state must be a dict: {self.state!r}'
            raise TypeError(message)
