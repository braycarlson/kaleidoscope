from __future__ import annotations

import enum
import logging

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeGuard

from django.db.models import Model
from django.db.models.query import QuerySet
from django.utils.functional import LazyObject, empty

if TYPE_CHECKING:
    from typing import Any


CONTEXT_CHILD_PREVIEW_LENGTH_MAX = 120
CONTEXT_CHILDREN_MAX = 100
CONTEXT_QUERYSET_PREVIEW_MAX = 25
CONTEXT_STRING_LENGTH_MAX = 10_000
RESOLVE_STEPS_MAX = 64
_SEQUENCE_TYPES = (list, tuple, set, frozenset)

logger = logging.getLogger(__name__)


class StepKind(StrEnum):
    ATTR = 'attr'
    ITEM = 'item'
    KEY = 'key'


class ValueKind(StrEnum):
    BOOL = 'bool'
    CALLABLE = 'callable'
    DICT = 'dict'
    ENUM = 'enum'
    ERROR = 'error'
    LAZY = 'lazy'
    LIST = 'list'
    MODEL = 'model'
    NONE = 'none'
    NUMBER = 'number'
    OBJECT = 'object'
    QUERYSET = 'queryset'
    REPR = 'repr'
    SET = 'set'
    STRING = 'string'
    TUPLE = 'tuple'


@dataclass(frozen=True, slots=True)
class Step:
    kind: StepKind
    index: int = 0
    name: str = ''

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StepKind):
            message = f'a step kind must be a StepKind: {self.kind!r}'
            raise TypeError(message)

        if isinstance(self.index, bool):
            message = f'a step index must be an integer, not a bool: {self.index!r}'
            raise TypeError(message)

        if not isinstance(self.index, int):
            message = f'a step index must be an integer: {self.index!r}'
            raise TypeError(message)

        if not isinstance(self.name, str):
            message = f'a step name must be text: {self.name!r}'
            raise TypeError(message)


def _callable_name(value: object) -> str:
    qualname = getattr(value, '__qualname__', None)

    if isinstance(qualname, str):
        if qualname:
            return qualname

    name = getattr(value, '__name__', None)

    if isinstance(name, str):
        if name:
            return name

    return type(value).__name__


def _child(label: str, value: object, step: dict) -> dict:
    if not isinstance(label, str):
        message = f'a child label must be text: {label!r}'
        raise TypeError(message)

    if not isinstance(step, dict):
        message = f'a child step must be a dict: {step!r}'
        raise TypeError(message)

    return {
        'label': label,
        'preview': preview(value),
        'has_children': has_children(value),
        'step': step,
    }


def _child_attribute(name: str, value: object) -> dict:
    step = {'kind': StepKind.ATTR, 'name': name}

    return _child(name, value, step)


def _child_item(label: str, index: int, value: object) -> dict:
    if index < 0:
        message = f'a child index must not be negative: {index}'
        raise ValueError(message)

    step = {'kind': StepKind.ITEM, 'index': index}

    return _child(label, value, step)


def _index_validate(index: int, count: int) -> None:
    if count < 0:
        message = f'an item count must not be negative: {count}'
        raise ValueError(message)

    if index < 0:
        raise IndexError(index)

    if index >= count:
        raise IndexError(index)


def _is_enum_class(value: object) -> TypeGuard[type[enum.Enum]]:
    if not isinstance(value, type):
        return False

    return issubclass(value, enum.Enum)


def _is_public_name(name: object) -> bool:
    if not isinstance(name, str):
        return False

    return not name.startswith('_')


def _lazy_unwrapped(value: object) -> tuple[object, bool]:
    if not issubclass(type(value), LazyObject):
        return value, False

    wrapped = value._wrapped  # ty:ignore[unresolved-attribute]

    if wrapped is empty:
        return value, True

    return wrapped, False


def _preview_complex(value: object) -> str:
    class_name = type(value).__name__

    if isinstance(value, str):
        return repr(value)

    if isinstance(value, QuerySet):
        return f'<QuerySet [{_queryset_model_name(value)}]>'

    if isinstance(value, Model):
        return f'<{class_name} pk={getattr(value, "pk", None)}>'

    if isinstance(value, dict):
        return f'dict[{len(value)}]'

    if isinstance(value, tuple):
        return f'tuple[{len(value)}]'

    if isinstance(value, list):
        return f'list[{len(value)}]'

    if isinstance(value, (set, frozenset)):
        return f'set[{len(value)}]'

    if _is_enum_class(value):
        return f'<{value.__name__}[{len(value)}]>'

    if callable(value):
        return f'<fn {_callable_name(value)}>'

    return _repr_safe(value)


def _preview_simple(value: object) -> str | None:
    if value is None:
        return 'None'

    if isinstance(value, bool):
        return 'True' if value else 'False'

    if isinstance(value, (int, float)):
        return repr(value)

    return None


def _queryset_model_name(value: QuerySet) -> str:
    if not isinstance(value, QuerySet):
        message = f'a model name comes from a QuerySet, not {type(value).__name__}'
        raise TypeError(message)

    model = value.model

    if model is None:
        return ''

    return model.__name__


def _repr_safe(value: object) -> str:
    class_name = type(value).__name__

    try:
        text = repr(value)
    except Exception:
        return f'<{class_name}>'

    if text.startswith('<'):
        if ' object at 0x' in text:
            return f'<{class_name}>'

    return text


def _resolve_step(current: Any, step: Step) -> Any:
    if not isinstance(step, Step):
        message = f'a path is resolved one Step at a time, not {type(step).__name__}'
        raise TypeError(message)

    if step.kind is StepKind.KEY:
        if not isinstance(current, dict):
            raise KeyError(step.name)

        if step.name not in current:
            raise KeyError(step.name)

        return current[step.name]

    if step.kind is StepKind.ATTR:
        return getattr(current, step.name)

    return _resolve_step_item(current, step.index)


def _resolve_step_item(current: Any, index: int) -> Any:
    if isinstance(index, bool):
        message = f'an item index must be an integer, not a bool: {index!r}'
        raise TypeError(message)

    if not isinstance(index, int):
        message = f'an item index must be an integer: {index!r}'
        raise TypeError(message)

    if isinstance(current, QuerySet):
        _index_validate(index, CONTEXT_QUERYSET_PREVIEW_MAX)

        return current[index]

    if isinstance(current, dict):
        entries = list(current.items())

        _index_validate(index, len(entries))

        return entries[index][1]

    if isinstance(current, (list, tuple)):
        _index_validate(index, len(current))

        return current[index]

    if isinstance(current, (set, frozenset)):
        entries = list(current)

        _index_validate(index, len(entries))

        return entries[index]

    if _is_enum_class(current):
        members = list(current)

        _index_validate(index, len(members))

        return members[index].value

    message = 'Not indexable'
    raise TypeError(message)


def _serialize(value: object) -> dict:
    scalar = _serialize_scalar(value)

    if scalar is not None:
        return scalar

    if isinstance(value, QuerySet):
        return _serialize_queryset(value)

    if isinstance(value, Model):
        return _serialize_model(value)

    if isinstance(value, dict):
        return _serialize_dict(value)

    if isinstance(value, _SEQUENCE_TYPES):
        return _serialize_sequence(value)

    return _serialize_fallback(value)


def _serialize_dict(value: dict) -> dict:
    if not isinstance(value, dict):
        message = f'a dict serializer needs a dict, not {type(value).__name__}'
        raise TypeError(message)

    entries = []
    truncated = 0

    for index, (key, item) in enumerate(value.items()):
        if index >= CONTEXT_CHILDREN_MAX:
            truncated = len(value) - CONTEXT_CHILDREN_MAX
            break

        label = key if isinstance(key, str) else _repr_safe(key)
        child = _child_item(label, index, item)

        entries.append(child)

    return {'type': ValueKind.DICT, 'size': len(value), 'items': entries, 'truncated': truncated}


def _serialize_enum_class(value: type[enum.Enum]) -> dict:
    if not _is_enum_class(value):
        message = f'an enum serializer needs an Enum class, not {value!r}'
        raise TypeError(message)

    members = list(value)
    entries = []
    truncated = 0

    for index, member in enumerate(members):
        if index >= CONTEXT_CHILDREN_MAX:
            truncated = len(members) - CONTEXT_CHILDREN_MAX
            break

        child = _child_item(member.name, index, member.value)

        entries.append(child)

    return {
        'type': ValueKind.ENUM,
        'class_name': value.__name__,
        'size': len(members),
        'items': entries,
        'truncated': truncated,
    }


def _serialize_fallback(value: object) -> dict:
    if _is_enum_class(value):
        return _serialize_enum_class(value)

    if callable(value):
        return {'type': ValueKind.CALLABLE, 'name': _callable_name(value)}

    try:
        attributes = vars(value)
    except TypeError:
        attributes = None

    if attributes:
        return _serialize_object(value, attributes)

    text, truncated = _text_split(_repr_safe(value))

    return {'type': ValueKind.REPR, 'value': text, 'truncated': truncated}


def _serialize_model(value: Model) -> dict:
    if not isinstance(value, Model):
        message = f'a model serializer needs a Model, not {type(value).__name__}'
        raise TypeError(message)

    class_name = type(value).__name__
    entries = []
    truncated = 0

    try:
        fields = value._meta.concrete_fields  # ty:ignore[unresolved-attribute]
    except Exception:
        fields = []

    for field in fields:
        if len(entries) >= CONTEXT_CHILDREN_MAX:
            truncated += 1
            continue

        name = getattr(field, 'attname', None) or getattr(field, 'name', None)

        if not name:
            continue

        try:
            item = getattr(value, name)
        except Exception:
            logger.exception('Kaleidoscope could not read the %s field of %s', name, class_name)
            continue

        child = _child_attribute(name, item)

        entries.append(child)

    return {
        'type': ValueKind.MODEL,
        'class_name': class_name,
        'pk': repr(getattr(value, 'pk', None)),
        'attributes': entries,
        'truncated': truncated,
    }


def _serialize_object(value: object, attributes: dict) -> dict:
    if not isinstance(attributes, dict):
        message = f'object attributes must be a dict: {attributes!r}'
        raise TypeError(message)

    entries = []
    truncated = 0

    for name, item in attributes.items():
        if not _is_public_name(name):
            continue

        if len(entries) >= CONTEXT_CHILDREN_MAX:
            truncated += 1
            continue

        child = _child_attribute(name, item)

        entries.append(child)

    return {
        'type': ValueKind.OBJECT,
        'class_name': type(value).__name__,
        'attributes': entries,
        'truncated': truncated,
    }


def _serialize_queryset(value: QuerySet) -> dict:
    if not isinstance(value, QuerySet):
        message = f'a queryset serializer needs a QuerySet, not {type(value).__name__}'
        raise TypeError(message)

    model_name = _queryset_model_name(value)

    try:
        items = list(value[:CONTEXT_QUERYSET_PREVIEW_MAX])
    except Exception as exception:
        return {
            'type': ValueKind.QUERYSET,
            'model': model_name,
            'error': str(exception),
            'items': [],
            'size': 0,
            'truncated': 0,
        }

    try:
        size = value.count()
    except Exception:
        size = len(items)

    entries = [_child_item(f'[{index}]', index, item) for index, item in enumerate(items)]

    return {
        'type': ValueKind.QUERYSET,
        'model': model_name,
        'size': size,
        'items': entries,
        'truncated': max(0, size - len(items)),
    }


def _serialize_scalar(value: object) -> dict | None:
    if value is None:
        return {'type': ValueKind.NONE}

    if isinstance(value, bool):
        return {'type': ValueKind.BOOL, 'value': value}

    if isinstance(value, (int, float)):
        return {'type': ValueKind.NUMBER, 'repr': repr(value)}

    if isinstance(value, str):
        text, truncated = _text_split(value)

        return {'type': ValueKind.STRING, 'value': text, 'truncated': truncated}

    return None


def _serialize_sequence(value: list | tuple | set | frozenset) -> dict:
    if not isinstance(value, _SEQUENCE_TYPES):
        message = f'a sequence serializer needs a sequence, not {type(value).__name__}'
        raise TypeError(message)

    if isinstance(value, tuple):
        kind = ValueKind.TUPLE
    elif isinstance(value, (set, frozenset)):
        kind = ValueKind.SET
    else:
        kind = ValueKind.LIST

    items = list(value)
    entries = []
    truncated = 0

    for index, item in enumerate(items):
        if index >= CONTEXT_CHILDREN_MAX:
            truncated = len(items) - CONTEXT_CHILDREN_MAX
            break

        child = _child_item(f'[{index}]', index, item)

        entries.append(child)

    return {'type': kind, 'size': len(items), 'items': entries, 'truncated': truncated}


def _step_parse(raw: object) -> Step:
    if not isinstance(raw, dict):
        message = 'Invalid step'
        raise TypeError(message)

    kind = StepKind(raw.get('kind'))

    if kind is StepKind.ITEM:
        return Step(kind, index=raw.get('index', -1))

    name = raw.get('name')

    if not isinstance(name, str):
        message = 'The step name must be a string'
        raise TypeError(message)

    if kind is StepKind.ATTR:
        if name.startswith('_'):
            message = f'The private attribute {name!r} is not inspectable'
            raise ValueError(message)

    return Step(kind, name=name)


def _text_split(text: str) -> tuple[str, int]:
    if not isinstance(text, str):
        message = f'text to split must be text: {text!r}'
        raise TypeError(message)

    if len(text) <= CONTEXT_STRING_LENGTH_MAX:
        return text, 0

    return text[:CONTEXT_STRING_LENGTH_MAX], len(text) - CONTEXT_STRING_LENGTH_MAX


def _has_children(value: object) -> bool:
    if isinstance(value, (QuerySet, Model)):
        return True

    if isinstance(value, (dict, *_SEQUENCE_TYPES)):
        return len(value) > 0

    if isinstance(value, (str, int, float, bool)):
        return False

    if value is None:
        return False

    if _is_enum_class(value):
        return len(value) > 0

    if callable(value):
        return False

    try:
        attributes = vars(value)
    except TypeError:
        return False

    return any(_is_public_name(name) for name in attributes)


def has_children(value: object) -> bool:
    try:
        resolved, pending = _lazy_unwrapped(value)
        present = False if pending else _has_children(resolved)
    except Exception:
        present = False

    return present


def preview(value: object) -> str:
    try:
        resolved, pending = _lazy_unwrapped(value)
        text = '<lazy>' if pending else _preview_simple(resolved)

        if text is None:
            text = _preview_complex(resolved)
    except Exception:
        text = f'<{type(value).__name__}>'

    if len(text) > CONTEXT_CHILD_PREVIEW_LENGTH_MAX:
        text = text[:CONTEXT_CHILD_PREVIEW_LENGTH_MAX - 1] + '…'

    return text


def resolve_path(root: Any, steps_raw: list) -> Any:
    if not isinstance(steps_raw, list):
        message = f'a path must be a list of steps: {steps_raw!r}'
        raise TypeError(message)

    if len(steps_raw) > RESOLVE_STEPS_MAX:
        message = f'a path holds at most {RESOLVE_STEPS_MAX} steps, not {len(steps_raw)}'
        raise ValueError(message)

    steps = [_step_parse(raw) for raw in steps_raw]
    current: Any = root

    for step in steps:
        current = _resolve_step(current, step)

    return current


def serialize(value: object) -> dict:
    try:
        resolved, pending = _lazy_unwrapped(value)
        serialized = {'type': ValueKind.LAZY} if pending else _serialize(resolved)
    except Exception:
        serialized = {'type': ValueKind.ERROR, 'class_name': type(value).__name__}

    if not isinstance(serialized.get('type'), ValueKind):
        message = f'a serialized value must carry a ValueKind type: {serialized!r}'
        raise TypeError(message)

    return serialized
