from __future__ import annotations

import uuid

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KaleidoscopeContext:
    is_ajax: bool = False
    request_id: str = ''
    asgi: bool = False
    state: dict[str, Any] = field(default_factory=dict)


def create_context(is_ajax: bool, asgi: bool) -> KaleidoscopeContext:
    return KaleidoscopeContext(
        is_ajax=is_ajax,
        request_id=uuid.uuid4().hex,
        asgi=asgi,
    )
