from __future__ import annotations

import functools
import json

from pathlib import Path
from types import MappingProxyType


CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'kaleidoscope/ui/tests/contract/panels.json'
ERRORS_MAX = 50
NODES_MAX = 1_000_000

TYPE_CLASSES = MappingProxyType({
    'array': (list,),
    'boolean': (bool,),
    'integer': (int,),
    'null': (type(None),),
    'number': (int, float),
    'object': (dict,),
    'string': (str,),
})


def _node_errors(value: object, node: dict, path: str, stack: list) -> list[str]:
    types = node.get('type')

    if types is None:
        return []

    allowed = types if isinstance(types, list) else [types]

    if not any(_type_matches(value, name) for name in allowed):
        return [f'{path}: expected {"|".join(allowed)}, got {type(value).__name__}']

    if isinstance(value, dict):
        return _object_errors(value, node, path, stack)

    if isinstance(value, list):
        items = node.get('items', {})

        for index, item in enumerate(value):
            entry = (item, items, f'{path}[{index}]')

            stack.append(entry)

    return []


def _object_errors(value: dict, node: dict, path: str, stack: list) -> list[str]:
    errors = [f'{path}: missing {key!r}' for key in node.get('required', []) if key not in value]
    properties = node.get('properties', {})
    additional = node.get('additionalProperties', {})

    for key, item in value.items():
        if key in properties:
            entry = (item, properties[key], f'{path}.{key}')

            stack.append(entry)
        elif additional is False:
            errors.append(f'{path}: unexpected {key!r}')
        else:
            entry = (item, additional, f'{path}.{key}')

            stack.append(entry)

    return errors


def _type_matches(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return name == 'boolean'

    return isinstance(value, TYPE_CLASSES[name])


@functools.cache
def contract_load() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))


def contract_errors(entry: dict, value: object) -> list[str]:
    variants = entry.get('variants', [entry])
    errors_closest: list[str] | None = None

    for variant in variants:
        errors = schema_errors(value, variant)

        if not errors:
            return []

        if errors_closest is not None:
            if len(errors) >= len(errors_closest):
                continue

        errors_closest = errors

    return errors_closest or []


def schema_errors(value: object, schema: dict) -> list[str]:
    errors: list[str] = []
    stack: list[tuple[object, dict, str]] = [(value, schema, '$')]

    for _ in range(NODES_MAX):
        if not stack:
            break

        if len(errors) >= ERRORS_MAX:
            break

        current, node, path = stack.pop()

        errors.extend(_node_errors(current, node, path, stack))

    return errors
