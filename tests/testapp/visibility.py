from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest


HEADER_HIDDEN = 'X-Kaleidoscope-Hidden'


def toolbar_visible(request: HttpRequest) -> bool:
    return request.headers.get(HEADER_HIDDEN) != '1'
