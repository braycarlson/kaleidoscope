from __future__ import annotations

import threading

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable


_patch_lock = threading.Lock()


def is_patched(function: object) -> bool:
    return getattr(function, '_kaleidoscope_patched', False) is True


def method_patch(owner: type, name: str, wrapper_build: Callable[[Callable], Callable]) -> None:
    if not isinstance(owner, type):
        message = f'a patched method needs a class to live on, not {type(owner).__name__}'
        raise TypeError(message)

    if not isinstance(name, str):
        message = f'a patched method name must be text: {name!r}'
        raise TypeError(message)

    with _patch_lock:
        method = vars(owner).get(name)

        if method is None:
            return

        if is_patched(method):
            return

        wrapper = wrapper_build(method)

        if not is_patched(wrapper):
            message = f'the wrapper for {owner.__qualname__}.{name} carries no kaleidoscope mark'
            raise RuntimeError(message)

        setattr(owner, name, wrapper)


def method_unpatch(owner: type, name: str) -> None:
    if not isinstance(owner, type):
        message = f'a patched method needs a class to live on, not {type(owner).__name__}'
        raise TypeError(message)

    with _patch_lock:
        method = vars(owner).get(name)

        if not is_patched(method):
            return

        setattr(owner, name, method.__wrapped__)  # ty:ignore[unresolved-attribute]


def patch_marked(wrapper: Callable) -> Callable:
    if not callable(wrapper):
        message = f'a patch must be callable, not {type(wrapper).__name__}'
        raise TypeError(message)

    if not hasattr(wrapper, '__wrapped__'):
        message = f'a patch must name the method it wraps: {wrapper!r}'
        raise ValueError(message)

    wrapper._kaleidoscope_patched = True  # ty:ignore[invalid-assignment]

    return wrapper
