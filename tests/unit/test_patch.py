from __future__ import annotations

import functools

import pytest

from typing import TYPE_CHECKING

from kaleidoscope.patch import is_patched, method_patch, method_unpatch, patch_marked

if TYPE_CHECKING:
    from collections.abc import Callable


def _target_built() -> type:
    class Target:
        def greeting(self) -> str:
            return 'hello'

    return Target


def _wrapper_bare_build(original: Callable) -> Callable:
    @functools.wraps(original)
    def wrapper(*arguments: object, **keywords: object) -> object:
        return original(*arguments, **keywords)

    return wrapper


def _wrapper_marked_build(original: Callable) -> Callable:
    return patch_marked(_wrapper_bare_build(original))


def test_a_method_is_wrapped_once_and_restored_on_request() -> None:
    target = _target_built()
    original = vars(target)['greeting']

    method_patch(target, 'greeting', _wrapper_marked_build)
    method_patch(target, 'greeting', _wrapper_marked_build)

    wrapped = vars(target)['greeting']

    method_unpatch(target, 'greeting')
    method_unpatch(target, 'greeting')

    assert is_patched(wrapped)
    assert wrapped.__wrapped__ is original
    assert target().greeting() == 'hello'
    assert vars(target)['greeting'] is original


def test_a_method_the_class_does_not_define_is_left_alone() -> None:
    target = _target_built()
    built: list[Callable] = []

    def build(original: Callable) -> Callable:
        built.append(original)

        return _wrapper_marked_build(original)

    method_patch(target, '__repr__', build)

    assert built == []
    assert '__repr__' not in vars(target)


def test_a_wrapper_without_the_mark_is_refused() -> None:
    target = _target_built()

    with pytest.raises(RuntimeError, match='greeting carries no kaleidoscope mark'):
        method_patch(target, 'greeting', _wrapper_bare_build)


@pytest.mark.parametrize(
    ('owner', 'name', 'pattern'),
    [
        (object(), 'greeting', 'needs a class to live on, not object'),
        (_target_built(), 7, 'a patched method name must be text: 7'),
    ],
)
def test_patching_refuses_an_owner_or_a_name_of_the_wrong_kind(
    owner: object,
    name: object,
    pattern: str,
) -> None:
    with pytest.raises(TypeError, match=pattern):
        method_patch(owner, name, _wrapper_marked_build)  # ty:ignore[invalid-argument-type]


def test_unpatching_refuses_an_owner_that_is_no_class() -> None:
    with pytest.raises(TypeError, match='needs a class to live on, not object'):
        method_unpatch(object(), 'greeting')  # ty:ignore[invalid-argument-type]


def test_a_mark_needs_a_callable_that_names_what_it_wraps() -> None:
    def unwrapping() -> None:
        return None

    with pytest.raises(TypeError, match='a patch must be callable, not NoneType'):
        patch_marked(None)  # ty:ignore[invalid-argument-type]

    with pytest.raises(ValueError, match='must name the method it wraps'):
        patch_marked(unwrapping)
