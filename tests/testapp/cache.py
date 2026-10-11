from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.cache.backends.locmem import LocMemCache

if TYPE_CHECKING:
    from collections.abc import Callable


fault_hook: Callable[[str], None] | None = None


def _fault_roll(operation: str) -> None:
    if fault_hook is not None:
        fault_hook(operation)


class FaultCache(LocMemCache):
    def add(self, key: str, value: Any, timeout: Any = None, version: int | None = None) -> bool:
        _fault_roll('add')

        return super().add(key, value, timeout, version)

    def clear(self) -> None:
        _fault_roll('clear')

        super().clear()

    def delete(self, key: str, version: int | None = None) -> bool:
        _fault_roll('delete')

        return super().delete(key, version)

    def get(self, key: str, default: Any = None, version: int | None = None) -> Any:
        _fault_roll('get')

        return super().get(key, default, version)

    def has_key(self, key: str, version: int | None = None) -> bool:
        _fault_roll('has_key')

        return super().has_key(key, version)

    def incr(self, key: str, delta: int = 1, version: int | None = None) -> int:
        _fault_roll('incr')

        return super().incr(key, delta, version)

    def set(self, key: str, value: Any, timeout: Any = None, version: int | None = None) -> None:
        _fault_roll('set')

        super().set(key, value, timeout, version)
