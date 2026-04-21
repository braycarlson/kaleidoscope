from __future__ import annotations

import enum

from typing import TYPE_CHECKING

from django.db.models import Model
from django.db.models.query import QuerySet

from kaleidoscope.constants import (
    CONTEXT_CHILD_PREVIEW_MAX_LENGTH,
    CONTEXT_CHILDREN_MAX,
    CONTEXT_QUERYSET_PREVIEW_MAX,
    CONTEXT_STRING_MAX_LENGTH,
)

if TYPE_CHECKING:
    from typing import Any


def _is_enum_class(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, enum.Enum)


class Serializer:
    def _preview_simple(self, value: object) -> str | None:
        if value is None:
            return 'None'

        if isinstance(value, bool):
            return 'True' if value else 'False'

        if isinstance(value, (int, float)):
            return repr(value)

        if type(value).__name__ == 'SimpleLazyObject':
            return '<lazy>'

        return None

    def _preview_complex(self, value: object) -> str:
        class_name = type(value).__name__

        if isinstance(value, str):
            return repr(value)

        if isinstance(value, QuerySet):
            return f'<QuerySet [{value.model.__name__}]>'

        if isinstance(value, Model):
            pk = getattr(value, 'pk', None)
            return f'<{class_name} pk={pk}>'

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
            name = (
                getattr(value, '__qualname__', None)
                or getattr(value, '__name__', class_name)
            )
            return f'<fn {name}>'

        try:
            repr_value = repr(value)
        except Exception:
            repr_value = f'<{class_name}>'

        if repr_value.startswith('<') and ' object at 0x' in repr_value:
            return f'<{class_name}>'

        return repr_value

    def preview(self, value: object) -> str:
        try:
            simple = self._preview_simple(value)

            if simple is not None:
                text = simple
            else:
                text = self._preview_complex(value)
        except Exception:
            text = f'<{type(value).__name__}>'

        if len(text) > CONTEXT_CHILD_PREVIEW_MAX_LENGTH:
            text = text[:CONTEXT_CHILD_PREVIEW_MAX_LENGTH - 1] + '…'

        return text

    def has_children(self, value: object) -> bool:
        try:
            if isinstance(value, QuerySet):
                return True

            if isinstance(value, Model):
                return True

            if isinstance(value, (dict, list, tuple, set, frozenset)):
                return len(value) > 0

            if isinstance(value, (str, int, float, bool)) or value is None:
                return False

            if _is_enum_class(value):
                return len(value) > 0

            if callable(value):
                return False

            try:
                var_dict = vars(value)
            except TypeError:
                return False

            return any(
                isinstance(key, str) and not key.startswith('_')
                for key in var_dict
            )
        except Exception:
            return False

    def truncate_string(self, text: str) -> tuple[str, int]:
        if len(text) <= CONTEXT_STRING_MAX_LENGTH:
            return text, 0

        return text[:CONTEXT_STRING_MAX_LENGTH], len(text) - CONTEXT_STRING_MAX_LENGTH

    def _serialize_model(self, value: Model) -> dict:
        class_name = type(value).__name__
        pk = getattr(value, 'pk', None)

        fields = []
        truncated = 0
        added = 0

        try:
            meta_fields = value._meta.concrete_fields
        except Exception:
            meta_fields = []

        for field in meta_fields:
            if added >= CONTEXT_CHILDREN_MAX:
                truncated += 1
                continue

            try:
                field_name = field.attname
            except AttributeError:
                field_name = getattr(field, 'name', None)

            if not field_name:
                continue

            try:
                field_value = getattr(value, field_name)
            except Exception:  # noqa: S112
                continue

            fields.append({
                'label': field_name,
                'preview': self.preview(field_value),
                'has_children': self.has_children(field_value),
                'step': {'kind': 'attr', 'name': field_name},
            })
            added += 1

        return {
            'type': 'model',
            'class_name': class_name,
            'pk': repr(pk),
            'attributes': fields,
            'truncated': truncated,
        }

    def _serialize_queryset(self, value: QuerySet) -> dict:
        model_name = value.model.__name__

        try:
            items_raw = list(value[:CONTEXT_QUERYSET_PREVIEW_MAX])
        except Exception as exception:
            return {
                'type': 'queryset',
                'model': model_name,
                'error': str(exception),
                'items': [],
                'size': 0,
                'truncated': 0,
            }

        try:
            total = value.count()
        except Exception:
            total = len(items_raw)

        entries = []

        for index, item in enumerate(items_raw):
            entries.append({
                'label': f'[{index}]',
                'preview': self.preview(item),
                'has_children': self.has_children(item),
                'step': {'kind': 'item', 'index': index},
            })

        truncated = max(0, total - len(items_raw))

        return {
            'type': 'queryset',
            'model': model_name,
            'size': total,
            'items': entries,
            'truncated': truncated,
        }

    def _serialize_dict(self, value: dict) -> dict:
        entries = []
        truncated = 0

        for index, (key, val) in enumerate(value.items()):
            if index >= CONTEXT_CHILDREN_MAX:
                truncated = len(value) - CONTEXT_CHILDREN_MAX
                break

            try:
                key_label = key if isinstance(key, str) else repr(key)
            except Exception:
                key_label = f'<{type(key).__name__}>'

            entries.append({
                'label': key_label,
                'preview': self.preview(val),
                'has_children': self.has_children(val),
                'step': {'kind': 'item', 'index': index},
            })

        return {
            'type': 'dict',
            'size': len(value),
            'items': entries,
            'truncated': truncated,
        }

    def _serialize_sequence(self, value: list | tuple | set | frozenset) -> dict:
        if isinstance(value, tuple):
            kind = 'tuple'
        elif isinstance(value, (set, frozenset)):
            kind = 'set'
        else:
            kind = 'list'

        collection = list(value)
        entries = []
        truncated = 0

        for index, item in enumerate(collection):
            if index >= CONTEXT_CHILDREN_MAX:
                truncated = len(collection) - CONTEXT_CHILDREN_MAX
                break

            entries.append({
                'label': f'[{index}]',
                'preview': self.preview(item),
                'has_children': self.has_children(item),
                'step': {'kind': 'item', 'index': index},
            })

        return {
            'type': kind,
            'size': len(collection),
            'items': entries,
            'truncated': truncated,
        }

    def _serialize_enum_class(self, value: type[enum.Enum]) -> dict:
        members = list(value)
        entries = []
        truncated = 0

        for index, member in enumerate(members):
            if index >= CONTEXT_CHILDREN_MAX:
                truncated = len(members) - CONTEXT_CHILDREN_MAX
                break

            entries.append({
                'label': member.name,
                'preview': self.preview(member.value),
                'has_children': self.has_children(member.value),
                'step': {'kind': 'item', 'index': index},
            })

        return {
            'type': 'enum',
            'class_name': value.__name__,
            'size': len(members),
            'items': entries,
            'truncated': truncated,
        }

    def _serialize_object(self, value: object, var_dict: dict) -> dict:
        attributes = []
        truncated = 0
        added = 0

        for key, val in var_dict.items():
            if not isinstance(key, str) or key.startswith('_'):
                continue

            if added >= CONTEXT_CHILDREN_MAX:
                truncated += 1
                continue

            attributes.append({
                'label': key,
                'preview': self.preview(val),
                'has_children': self.has_children(val),
                'step': {'kind': 'attr', 'name': key},
            })
            added += 1

        return {
            'type': 'object',
            'class_name': type(value).__name__,
            'attributes': attributes,
            'truncated': truncated,
        }

    def _serialize_scalar(self, value: object) -> dict | None:
        if value is None:
            return {'type': 'none'}

        if isinstance(value, bool):
            return {'type': 'bool', 'value': value}

        if isinstance(value, (int, float)):
            return {'type': 'number', 'repr': repr(value)}

        if type(value).__name__ == 'SimpleLazyObject':
            return {'type': 'lazy'}

        if isinstance(value, str):
            text, truncated = self.truncate_string(value)
            return {'type': 'string', 'value': text, 'truncated': truncated}

        return None

    def _serialize_fallback(self, value: object) -> dict:
        class_name = type(value).__name__

        if _is_enum_class(value):
            return self._serialize_enum_class(value)

        if callable(value):
            name = (
                getattr(value, '__qualname__', None)
                or getattr(value, '__name__', class_name)
            )
            return {'type': 'callable', 'name': name}

        try:
            var_dict = vars(value)
        except TypeError:
            var_dict = None

        if var_dict:
            return self._serialize_object(value, var_dict)

        try:
            repr_value = repr(value)
        except Exception:
            repr_value = f'<{class_name}>'

        text, truncated = self.truncate_string(repr_value)
        return {'type': 'repr', 'value': text, 'truncated': truncated}

    def serialize(self, value: object) -> dict:
        try:
            scalar = self._serialize_scalar(value)

            if scalar is not None:
                return scalar

            if isinstance(value, QuerySet):
                return self._serialize_queryset(value)

            if isinstance(value, Model):
                return self._serialize_model(value)

            if isinstance(value, dict):
                return self._serialize_dict(value)

            if isinstance(value, (list, tuple, set, frozenset)):
                return self._serialize_sequence(value)

            return self._serialize_fallback(value)
        except Exception:
            return {'type': 'error', 'class_name': type(value).__name__}

    def _resolve_step_item(self, current: Any, step: dict) -> Any:
        index = int(step.get('index', -1))

        if isinstance(current, QuerySet):
            if index < 0 or index >= CONTEXT_QUERYSET_PREVIEW_MAX:
                raise IndexError(index)

            return current[index]

        if isinstance(current, dict):
            entries = list(current.items())

            if index < 0 or index >= len(entries):
                raise IndexError(index)

            return entries[index][1]

        if isinstance(current, (list, tuple)):
            return current[index]

        if isinstance(current, (set, frozenset)):
            entries = list(current)

            if index < 0 or index >= len(entries):
                raise IndexError(index)

            return entries[index]

        if _is_enum_class(current):
            members = list(current)

            if index < 0 or index >= len(members):
                raise IndexError(index)

            return members[index].value

        message = 'Not indexable'
        raise TypeError(message)

    def _resolve_step(self, current: Any, step: dict) -> Any:
        kind = step.get('kind')

        if kind == 'key':
            name = step.get('name')

            if not isinstance(current, dict) or name not in current:
                raise KeyError(name)

            return current[name]

        if kind == 'attr':
            name = step.get('name')

            if not isinstance(name, str):
                message = 'The attr name must be string'
                raise TypeError(message)

            return getattr(current, name)

        if kind == 'item':
            return self._resolve_step_item(current, step)

        message = f'Unknown step kind: {kind}'
        raise ValueError(message)

    def resolve_path(self, root: Any, steps: list) -> Any:
        current: Any = root

        for step in steps:
            if not isinstance(step, dict):
                message = 'Invalid step'
                raise TypeError(message)

            current = self._resolve_step(current, step)

        return current
