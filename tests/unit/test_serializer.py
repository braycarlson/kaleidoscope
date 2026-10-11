from __future__ import annotations

import enum
import functools

import pytest

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest import mock

from django.db.models.query import QuerySet
from django.utils.functional import SimpleLazyObject

from kaleidoscope import serializer
from kaleidoscope.serializer import (
    CONTEXT_CHILD_PREVIEW_LENGTH_MAX,
    CONTEXT_CHILDREN_MAX,
    CONTEXT_STRING_LENGTH_MAX,
    RESOLVE_STEPS_MAX,
    Step,
    StepKind,
    _callable_name,
    _child,
    _child_item,
    _index_validate,
    _queryset_model_name,
    _resolve_step,
    _resolve_step_item,
    _serialize_dict,
    _serialize_enum_class,
    _serialize_model,
    _serialize_object,
    _serialize_queryset,
    _serialize_sequence,
    _text_split,
    has_children,
    preview,
    resolve_path,
    serialize,
)

from tests.testapp.models import Author

if TYPE_CHECKING:
    from collections.abc import Callable


Many = enum.Enum('Many', [f'MEMBER_{index}' for index in range(CONTEXT_CHILDREN_MAX + 5)])


class Bracketed:
    def __repr__(self) -> str:
        return '<bracketed value>'


class Color(enum.Enum):
    RED = 'red'
    BLUE = 'blue'


class DictionaryRefusing(dict):
    def __len__(self) -> int:
        message = 'no length for you'
        raise RuntimeError(message)

    def items(self) -> object:
        message = 'no items for you'
        raise RuntimeError(message)


class FieldsRefusing:
    pk = SimpleNamespace(attname='id')

    @property
    def concrete_fields(self) -> list:
        message = 'no fields for you'
        raise RuntimeError(message)


class KeyedOddly:
    def __init__(self) -> None:
        self.__dict__[1] = 'numbered'
        self.shown = 'yes'


class VarsRefusing:
    @property
    def __dict__(self) -> dict:
        message = 'no attributes for you'
        raise RuntimeError(message)


class Plain:
    def __init__(self) -> None:
        self.visible = 1
        self._hidden = 2


class Slotted:
    __slots__ = ('value',)

    def __init__(self) -> None:
        self.value = 1


class Unprintable:
    def __repr__(self) -> str:
        message = 'no repr for you'
        raise RuntimeError(message)


def _function() -> None:
    pass


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (None, 'None'),
        (True, 'True'),
        (False, 'False'),
        (3, '3'),
        (1.5, '1.5'),
        ('text', "'text'"),
        ({'a': 1}, 'dict[1]'),
        ((1, 2), 'tuple[2]'),
        ([1, 2, 3], 'list[3]'),
        ({1}, 'set[1]'),
        (frozenset(), 'set[0]'),
        (Color, '<Color[2]>'),
        (_function, '<fn _function>'),
        (Plain(), '<Plain>'),
        (Unprintable(), '<Unprintable>'),
    ],
)
def test_preview_names_a_value_briefly(value: object, expected: str) -> None:
    assert preview(value) == expected


def test_preview_is_bounded() -> None:
    text = preview('x' * 10_000)

    assert len(text) == CONTEXT_CHILD_PREVIEW_LENGTH_MAX
    assert text.endswith('…')


@pytest.mark.django_db
def test_preview_names_models_and_querysets() -> None:
    author = Author.objects.create(name='previewed')

    assert preview(author) == f'<Author pk={author.pk}>'
    assert preview(Author.objects.all()) == '<QuerySet [Author]>'


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (None, False),
        (1, False),
        ('text', False),
        ({}, False),
        ({'a': 1}, True),
        ([], False),
        ([1], True),
        (Color, True),
        (_function, False),
        (Plain(), True),
        (Slotted(), False),
    ],
)
def test_has_children_marks_only_expandable_values(value: object, expected: bool) -> None:
    assert has_children(value) is expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (None, {'type': 'none'}),
        (True, {'type': 'bool', 'value': True}),
        (7, {'type': 'number', 'repr': '7'}),
        (float('nan'), {'type': 'number', 'repr': 'nan'}),
        ('text', {'type': 'string', 'truncated': 0, 'value': 'text'}),
        (_function, {'name': '_function', 'type': 'callable'}),
    ],
)
def test_serialize_describes_scalars(value: object, expected: dict) -> None:
    assert serialize(value) == expected


def test_serialize_truncates_long_strings() -> None:
    serialized = serialize('x' * (CONTEXT_STRING_LENGTH_MAX + 5))

    assert len(serialized['value']) == CONTEXT_STRING_LENGTH_MAX
    assert serialized['truncated'] == 5


def test_serialize_lists_container_children_up_to_the_maximum() -> None:
    serialized = serialize(list(range(CONTEXT_CHILDREN_MAX + 7)))

    assert serialized['type'] == 'list'
    assert serialized['size'] == CONTEXT_CHILDREN_MAX + 7
    assert len(serialized['items']) == CONTEXT_CHILDREN_MAX
    assert serialized['truncated'] == 7

    assert serialized['items'][3] == {
        'has_children': False,
        'label': '[3]',
        'preview': '3',
        'step': {'index': 3, 'kind': 'item'},
    }


def test_serialize_describes_public_object_attributes_only() -> None:
    plain = Plain()
    serialized = serialize(plain)

    assert serialized['type'] == 'object'
    assert [entry['label'] for entry in serialized['attributes']] == ['visible']


def test_serialize_describes_an_enum_class() -> None:
    serialized = serialize(Color)

    assert serialized['type'] == 'enum'
    assert [entry['label'] for entry in serialized['items']] == ['RED', 'BLUE']


@pytest.mark.django_db
def test_serialize_describes_a_queryset_and_a_model() -> None:
    authors = [Author.objects.create(name=f'author-{index}') for index in range(3)]
    queryset = serialize(Author.objects.order_by('pk'))
    model = serialize(authors[0])

    assert queryset['type'] == 'queryset'
    assert queryset['size'] == 3

    assert [entry['preview'] for entry in queryset['items']] == [
        f'<Author pk={author.pk}>' for author in authors
    ]

    assert model['type'] == 'model'
    assert [entry['label'] for entry in model['attributes']] == ['id', 'name']


def test_serialize_never_raises_on_an_unprintable_value() -> None:
    unprintable = Unprintable()
    serialized = serialize(unprintable)

    assert serialized['type'] in {'repr', 'error'}


def test_resolve_path_walks_keys_attributes_and_items() -> None:
    root = {'plain': Plain(), 'items': [10, 20, 30], 'pair': (1, 2), 'mapping': {'k': 'v'}}
    attribute_steps = [{'kind': 'key', 'name': 'plain'}, {'kind': 'attr', 'name': 'visible'}]
    item_steps = [{'kind': 'key', 'name': 'items'}, {'kind': 'item', 'index': 2}]
    mapping_steps = [{'kind': 'key', 'name': 'mapping'}, {'kind': 'item', 'index': 0}]
    enum_steps = [{'kind': 'item', 'index': 1}]

    assert resolve_path(root, attribute_steps) == 1
    assert resolve_path(root, item_steps) == 30
    assert resolve_path(root, mapping_steps) == 'v'
    assert resolve_path(Color, enum_steps) == 'blue'


@pytest.mark.parametrize(
    'steps',
    [
        [{'kind': 'key', 'name': 'missing'}],
        [{'kind': 'unknown'}],
        ['not a dict'],
        [{'kind': 'attr', 'name': 5}],
        [{'kind': 'key', 'name': 'items'}, {'kind': 'item', 'index': 99}],
        [{'kind': 'key', 'name': 'items'}, {'kind': 'item', 'index': 'x'}],
        [{'kind': 'key', 'name': 'plain'}, {'kind': 'attr', 'name': 'missing'}],
        [{'kind': 'key', 'name': 'plain'}, {'kind': 'item', 'index': 0}],
    ],
)
def test_resolve_path_raises_for_a_path_that_does_not_exist(steps: list) -> None:
    root = {'plain': Plain(), 'items': [1]}

    with pytest.raises((AttributeError, IndexError, KeyError, TypeError, ValueError)):
        resolve_path(root, steps)


@pytest.mark.parametrize('name', ['_hidden', '__class__', '__dict__', '__init__'])
def test_resolve_path_refuses_private_attributes(name: str) -> None:
    steps = [{'kind': 'key', 'name': 'plain'}, {'kind': 'attr', 'name': name}]

    with pytest.raises(ValueError, match='not inspectable'):
        resolve_path({'plain': Plain()}, steps)


def _lazy_build(calls: list[int]) -> SimpleLazyObject:
    def evaluated() -> dict:
        calls.append(1)

        return {'user': 'alice'}

    return SimpleLazyObject(evaluated)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (QuerySet(), '<QuerySet []>'),
        (Bracketed(), '<bracketed value>'),
        (functools.partial(_function), '<fn partial>'),
        (DictionaryRefusing(), '<DictionaryRefusing>'),
    ],
)
def test_preview_names_unusual_values_briefly(value: object, expected: str) -> None:
    assert preview(value) == expected


def test_an_unevaluated_lazy_value_is_never_forced() -> None:
    calls: list[int] = []
    lazy = _lazy_build(calls)

    assert preview(lazy) == '<lazy>'
    assert serialize(lazy) == {'type': 'lazy'}
    assert has_children(lazy) is False
    assert calls == []


def test_an_evaluated_lazy_value_shows_what_it_wraps() -> None:
    calls: list[int] = []
    lazy = _lazy_build(calls)
    _ = lazy['user']

    assert preview(lazy) == 'dict[1]'
    assert serialize(lazy)['type'] == 'dict'
    assert has_children(lazy) is True
    assert calls == [1]


def test_has_children_is_false_for_a_value_that_refuses_inspection() -> None:
    assert has_children(VarsRefusing()) is False


def test_serialize_truncates_a_large_dictionary_and_labels_every_key() -> None:
    value = {index: index for index in range(CONTEXT_CHILDREN_MAX + 3)}
    serialized = serialize(value)

    assert serialized['size'] == CONTEXT_CHILDREN_MAX + 3
    assert serialized['truncated'] == 3
    assert [item['label'] for item in serialized['items'][:2]] == ['0', '1']


def test_serialize_truncates_a_large_enum_class() -> None:
    serialized = serialize(Many)

    assert serialized['type'] == 'enum'
    assert len(serialized['items']) == CONTEXT_CHILDREN_MAX
    assert serialized['truncated'] == 5


def test_serialize_truncates_an_object_with_many_attributes() -> None:
    attributes = {f'field_{index}': index for index in range(CONTEXT_CHILDREN_MAX + 2)}
    value = SimpleNamespace(**attributes)
    serialized = serialize(value)

    assert serialized['type'] == 'object'
    assert len(serialized['attributes']) == CONTEXT_CHILDREN_MAX
    assert serialized['truncated'] == 2


def test_serialize_skips_attributes_whose_name_is_not_text() -> None:
    serialized = serialize(KeyedOddly())

    assert [attribute['label'] for attribute in serialized['attributes']] == ['shown']


def test_serialize_names_a_callable_without_a_qualified_name() -> None:
    assert serialize(functools.partial(_function)) == {'type': 'callable', 'name': 'partial'}


def test_serialize_reports_a_value_that_refuses_serialization_as_an_error() -> None:
    assert serialize(DictionaryRefusing()) == {'type': 'error', 'class_name': 'DictionaryRefusing'}


def test_serialize_survives_a_model_whose_fields_cannot_be_listed() -> None:
    author = Author(name='alice')
    meta = FieldsRefusing()

    with mock.patch.object(Author, '_meta', meta):
        serialized = serialize(author)

    assert serialized['type'] == 'model'
    assert serialized['attributes'] == []
    assert serialized['pk'] == 'None'


def test_serialize_skips_model_fields_it_cannot_name_or_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    author = Author(name='alice')
    unnamed = SimpleNamespace(attname=None, name=None)
    unreadable = SimpleNamespace(attname='missing_column', name='missing_column')
    readable = SimpleNamespace(attname='name', name='name')
    fields = [unnamed, unreadable, *([readable] * (CONTEXT_CHILDREN_MAX + 1))]
    meta = SimpleNamespace(concrete_fields=fields)

    with mock.patch.object(Author, '_meta', meta):
        serialized = serialize(author)

    assert len(serialized['attributes']) == CONTEXT_CHILDREN_MAX
    assert serialized['truncated'] == 1
    assert 'missing_column' in caplog.text


@pytest.mark.django_db
def test_serialize_reports_a_queryset_that_cannot_be_evaluated() -> None:
    queryset = Author.objects.extra(where=['no_such_column = 1'])
    serialized = serialize(queryset)

    assert serialized['type'] == 'queryset'
    assert serialized['items'] == []
    assert 'no_such_column' in serialized['error']


@pytest.mark.django_db
def test_serialize_sizes_a_queryset_by_its_items_when_counting_fails(library: list[Author]) -> None:
    _ = library

    with mock.patch.object(QuerySet, 'count', side_effect=RuntimeError('no count')):
        serialized = serialize(Author.objects.all())

    assert serialized['size'] == 3
    assert serialized['truncated'] == 0


def test_resolve_path_walks_into_a_set_by_its_iteration_order() -> None:
    root = {'tags': frozenset({'only'})}
    steps = [{'kind': 'key', 'name': 'tags'}, {'kind': 'item', 'index': 0}]

    assert resolve_path(root, steps) == 'only'


@pytest.mark.parametrize(
    'steps',
    [
        [{'kind': 'key', 'name': 'items'}, {'kind': 'item', 'index': -1}],
        [{'kind': 'key', 'name': 'items'}, {'kind': 'key', 'name': 'inner'}],
    ],
)
def test_resolve_path_refuses_a_negative_index_and_a_key_into_a_list(steps: list) -> None:
    with pytest.raises((IndexError, KeyError)):
        resolve_path({'items': [1, 2]}, steps)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ({3, 1}, {'type': 'set', 'size': 2}),
        (frozenset(), {'type': 'set', 'size': 0}),
        ((1, 2), {'type': 'tuple', 'size': 2}),
        (b'raw', {'type': 'repr', 'value': "b'raw'"}),
        (Slotted(), {'type': 'repr', 'value': '<Slotted>'}),
    ],
)
def test_serialize_describes_sets_tuples_and_values_without_attributes(
    value: object,
    expected: dict,
) -> None:
    serialized = serialize(value)

    assert {key: serialized[key] for key in expected} == expected


@pytest.mark.parametrize(
    ('arguments', 'pattern'),
    [
        ({'kind': 'item'}, 'step kind must be a StepKind'),
        ({'kind': StepKind.ITEM, 'index': True}, 'step index must be an integer, not a bool'),
        ({'kind': StepKind.ITEM, 'index': '1'}, 'step index must be an integer'),
        ({'kind': StepKind.KEY, 'name': 3}, 'step name must be text'),
    ],
)
def test_a_step_refuses_a_field_of_the_wrong_kind(arguments: dict, pattern: str) -> None:
    with pytest.raises(TypeError, match=pattern):
        Step(**arguments)


def test_a_callable_name_falls_back_past_names_that_are_not_text() -> None:
    named = SimpleNamespace(__qualname__=5, __name__='named')
    unnamed = SimpleNamespace(__qualname__=None, __name__=7)
    blank = SimpleNamespace(__qualname__='', __name__='')

    assert _callable_name(named) == 'named'
    assert _callable_name(unnamed) == 'SimpleNamespace'
    assert _callable_name(blank) == 'SimpleNamespace'


@pytest.mark.django_db
def test_resolve_path_walks_into_a_row_of_a_queryset(library: list[Author]) -> None:
    root = {'authors': Author.objects.order_by('pk')}
    steps = [{'kind': 'key', 'name': 'authors'}, {'kind': 'item', 'index': 1}]

    assert resolve_path(root, steps) == library[1]


@pytest.mark.parametrize(
    ('function', 'arguments', 'error', 'pattern'),
    [
        (_child, (3, 'value', {}), TypeError, 'child label must be text'),
        (_child, ('label', 'value', []), TypeError, 'child step must be a dict'),
        (_child_item, ('[0]', -1, 'value'), ValueError, 'child index must not be negative'),
        (_index_validate, (0, -1), ValueError, 'item count must not be negative'),
        (_queryset_model_name, ([],), TypeError, 'comes from a QuerySet, not list'),
        (_resolve_step, ({}, {'kind': 'key'}), TypeError, 'one Step at a time, not dict'),
        (_resolve_step_item, ([1], True), TypeError, 'item index must be an integer, not a bool'),
        (_resolve_step_item, ([1], '0'), TypeError, 'item index must be an integer'),
        (_serialize_dict, ([],), TypeError, 'dict serializer needs a dict, not list'),
        (_serialize_enum_class, (int,), TypeError, 'enum serializer needs an Enum class'),
        (_serialize_model, ({},), TypeError, 'model serializer needs a Model, not dict'),
        (_serialize_object, (object(), []), TypeError, 'object attributes must be a dict'),
        (_serialize_queryset, ([],), TypeError, 'queryset serializer needs a QuerySet, not list'),
        (_serialize_sequence, ({},), TypeError, 'sequence serializer needs a sequence, not dict'),
        (_text_split, (None,), TypeError, 'text to split must be text'),
    ],
)
def test_serializer_helpers_refuse_arguments_of_the_wrong_kind(
    function: Callable,
    arguments: tuple,
    error: type[Exception],
    pattern: str,
) -> None:
    with pytest.raises(error, match=pattern):
        function(*arguments)


def test_resolve_path_refuses_a_path_that_is_not_a_list_or_is_too_long() -> None:
    with pytest.raises(TypeError, match='path must be a list of steps'):
        resolve_path({}, ({'kind': 'key', 'name': 'a'},))  # ty:ignore[invalid-argument-type]

    steps = [{'kind': 'item', 'index': 0}] * (RESOLVE_STEPS_MAX + 1)

    with pytest.raises(ValueError, match=f'at most {RESOLVE_STEPS_MAX} steps'):
        resolve_path([[1]], steps)


def test_resolve_path_refuses_an_item_step_whose_index_is_a_bool() -> None:
    with pytest.raises(TypeError, match='not a bool'):
        resolve_path([1, 2], [{'kind': 'item', 'index': True}])


@pytest.mark.parametrize('answer', [{'type': 'bogus'}, {}])
def test_serialize_fails_loudly_when_a_branch_answers_without_a_value_kind(
    monkeypatch: pytest.MonkeyPatch,
    answer: dict,
) -> None:
    monkeypatch.setattr(serializer, '_serialize', lambda _value: answer)

    with pytest.raises(TypeError, match='must carry a ValueKind type'):
        serialize('anything')
