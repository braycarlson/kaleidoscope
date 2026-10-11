import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import { fetch_fake_create, settled, type FetchFake } from '../../support/fetch';
import { vue_reports } from '../../support/setup';

interface Loaded {
    fake: FetchFake;
    wrapper: VueWrapper;
}

const CHILD_AUTHOR = Object.freeze({
    has_children: true,
    label: 'author',
    preview: '<Author pk=1>',
    step: { kind: 'key', name: 'author' },
});

const CHILD_TITLE = Object.freeze({
    has_children: false,
    label: 'title',
    preview: "'Dune'",
    step: { kind: 'key', name: 'title' },
});

const CHILDREN = Object.freeze([CHILD_AUTHOR, CHILD_TITLE]);

const PATH_ROOT = Object.freeze([{ kind: 'key', name: 'book' }]);

async function node_mount(props: Record<string, unknown>): Promise<Loaded> {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../../src/components/panels/ValueNode.vue');
    const wrapper = mount(module.default as Component, {
        props: { path: [...PATH_ROOT], template_index: 0, ...props },
    }) as VueWrapper;

    await flushPromises();

    return { fake, wrapper };
}

async function node_reported(props: Record<string, unknown>): Promise<string> {
    let thrown = '';

    try {
        await node_mount(props);
    } catch (error: unknown) {
        thrown = String(error);
    }

    return [thrown, ...vue_reports.splice(0)].join('\n');
}

function child_with(step: unknown) {
    return { has_children: false, label: 'a', preview: 'b', step: step };
}

function path_of(url: string): unknown {
    return JSON.parse(new URL(url, 'http://localhost').searchParams.get('path') ?? 'null');
}

describe('ValueNode leaves', function() {
    it.each([
        [{ type: 'none' }, 'None'],
        [{ type: 'bool', value: true }, 'True'],
        [{ type: 'bool', value: false }, 'False'],
        [{ type: 'number', repr: '1.5' }, '1.5'],
        [{ type: 'string', truncated: 0, value: "it's" }, "'it\\'s'"],
        [{ type: 'string', truncated: 9, value: 'cut' }, "'cut'  # ...+9 chars"],
        [{ type: 'lazy' }, '<lazy>'],
        [{ name: 'Book.save', type: 'callable' }, '<fn Book.save>'],
        [{ truncated: 3, type: 'repr', value: 'Path(x)' }, 'Path(x)  # ...+3 chars'],
        [{ class_name: 'Broken', type: 'error' }, '<Broken error>'],
        [{ type: 'unheard-of' }, ''],
    ])('shows %j as %s and never expands', async function(initial, expected) {
        const props = { initial: initial, label: 'value', separator: ':' };
        const { fake, wrapper } = await node_mount(props);

        await wrapper.trigger('click');

        expect(wrapper.text()).toBe('value:' + expected);
        expect(fake.calls).toEqual([]);
    });
});

describe('ValueNode containers', function() {
    it('loads its children on the first expansion only', async function() {
        const props = { has_children: true, label: 'book', preview: 'dict[2]' };
        const { fake, wrapper } = await node_mount(props);
        const row = wrapper.get('div.flex');

        expect(wrapper.text()).toBe('bookdict[2]');

        await row.trigger('click');

        expect(wrapper.text()).toContain('Loading...');

        const request = fake.take('/templates/action/value/');

        expect(path_of(request.url)).toEqual(PATH_ROOT);

        request.resolve(200, { value: { items: CHILDREN, size: 2, truncated: 4, type: 'dict' } });
        await settled();

        expect(wrapper.text()).toContain('dict[2]');
        expect(wrapper.text()).toContain('title');
        expect(wrapper.text()).toContain('... 4 more');

        await row.trigger('click');
        await row.trigger('click');

        expect(fake.calls).toHaveLength(1);
    });

    it('walks one step further for each child it expands', async function() {
        const initial = { items: CHILDREN, size: 2, truncated: 0, type: 'dict' };
        const props = { auto_expand: true, initial: initial, label: 'book' };
        const { fake, wrapper } = await node_mount(props);

        const author = wrapper.findAll('div.flex').find(function(row) {
            return row.text().startsWith('author');
        });

        await author?.trigger('click');

        const request = fake.take('/templates/action/value/');

        expect(path_of(request.url)).toEqual([...PATH_ROOT, { kind: 'key', name: 'author' }]);

        const value = { attributes: [], class_name: 'Author', pk: '1', type: 'model' };

        request.resolve(200, { value: value });
        await settled();

        expect(wrapper.text()).toContain('<Author pk=1>');
    });

});

describe('ValueNode container headers', function() {
    it.each([
        [{ class_name: 'Point', type: 'object' }, '<Point>'],
        [{ model: 'Book', size: 7, type: 'queryset' }, '<QuerySet [Book] size=7>'],
        [{ class_name: 'Color', size: 2, type: 'enum' }, '<Color[2]>'],
        [{ size: 1, type: 'list' }, 'list[1]'],
        [{ size: 2, type: 'tuple' }, 'tuple[2]'],
        [{ size: 3, type: 'set' }, 'set[3]'],
    ])('names an expanded %j as %s', async function(initial, expected) {
        const props = { auto_expand: true, initial: { items: [], ...initial } };
        const { wrapper } = await node_mount(props);

        expect(wrapper.text()).toBe(expected);
    });

    it('explains a queryset that failed to evaluate', async function() {
        const initial = {
            error: 'no such table',
            items: [],
            model: 'Book',
            size: 0,
            type: 'queryset',
        };

        const { wrapper } = await node_mount({ auto_expand: true, initial: initial });

        expect(wrapper.text()).toContain('QuerySet error: no such table');
    });
});

describe('ValueNode failures', function() {
    it('shows the error the server explains', async function() {
        const { fake, wrapper } = await node_mount({ auto_expand: true, label: 'book' });

        fake.take('/templates/action/value/').resolve(400, { error: 'path too deep' });
        await settled();

        expect(wrapper.text()).toContain('Error: path too deep');
    });

    it('shows the status when the server explains nothing', async function() {
        const { fake, wrapper } = await node_mount({ auto_expand: true, label: 'book' });

        fake.take('/templates/action/value/').resolve(502, 'not json');
        await settled();

        expect(wrapper.text()).toContain('Error: HTTP 502');
    });

    it('shows a network failure and stops offering to expand', async function() {
        const { fake, wrapper } = await node_mount({ has_children: true, label: 'book' });
        const row = wrapper.get('div.flex');

        await row.trigger('click');
        fake.take('/templates/action/value/').fail('Failed to fetch');
        await settled();

        expect(wrapper.text()).toContain('Error: TypeError: Failed to fetch');

        await row.trigger('click');
        await row.trigger('click');

        expect(fake.calls).toHaveLength(1);
    });
});

describe('ContextValueContainer', function() {
    it('shows nothing until a key is chosen, then expands that key', async function() {
        const fake = fetch_fake_create();

        vi.stubGlobal('fetch', fake.fetch);
        vi.resetModules();

        const module = await import('../../../src/components/panels/ContextValueContainer.vue');
        const props = { active_key: null, template_index: 3 };
        const wrapper = mount(module.default as Component, { props: props }) as VueWrapper;

        expect(wrapper.html()).not.toContain('ValueNode');
        expect(fake.calls).toEqual([]);

        await wrapper.setProps({ active_key: 'book' });
        await flushPromises();

        const request = fake.take('/templates/action/value/');

        expect(request.url).toContain('template=3');
        expect(path_of(request.url)).toEqual(PATH_ROOT);
    });
});

describe('PrismCode', function() {
    async function code_mount(props: Record<string, unknown>): Promise<VueWrapper> {
        vi.resetModules();

        const module = await import('../../../src/components/panels/PrismCode.vue');

        return mount(module.default as Component, { props: props }) as VueWrapper;
    }

    it('highlights python by default and sql on request', async function() {
        const python = await code_mount({ code: "def f(): return 'x'" });
        const sql = await code_mount({ block: true, code: 'SELECT 1 FROM book', language: 'sql' });

        expect(python.find('span.token.keyword').text()).toBe('def');
        expect(sql.find('pre code span.token.keyword').text()).toBe('SELECT');
        expect(sql.text()).toBe('SELECT 1 FROM book');
    });

    it('shows code of an unknown language as plain text', async function() {
        const wrapper = await code_mount({ code: 'plain <text>', language: 'brainfuck' });

        expect(wrapper.text()).toBe('plain <text>');
        expect(wrapper.find('span.token').exists()).toBe(false);
    });

    it('shows a token tree too deep to render as plain text', async function() {
        const prism = (await import('prismjs')).default;
        const group: Record<string, unknown> = { lookbehind: true, pattern: /(^\()[\s\S]*(?=\)$)/ };
        const grammar = { group: group };

        group['inside'] = grammar;
        prism.languages['nested'] = grammar as unknown as Prism.Grammar;

        const code = '('.repeat(40) + 'x' + ')'.repeat(40);
        const wrapper = await code_mount({ code: code, language: 'nested' });

        expect(wrapper.text()).toBe(code);
        expect(wrapper.find('span.token').exists()).toBe(false);
    });
});

describe('ValueNode separators and gaps', function() {
    it.each([
        ['object', '='],
        ['model', '='],
        ['enum', '='],
        ['list', ':'],
    ])('separates the children of a %s with %s', async function(type, separator) {
        const child = {
            has_children: false,
            label: 'field',
            preview: '1',
            step: { kind: 'attr', name: 'field' },
        };

        const initial = { attributes: [child], items: [child], type: type };
        const { wrapper } = await node_mount({ auto_expand: true, initial: initial });

        expect(wrapper.text()).toContain('field' + separator + '1');
    });

    it.each([
        [{ type: 'object' }, '<>'],
        [{ type: 'model' }, '< pk=>'],
        [{ type: 'queryset' }, '<QuerySet [] size=0>'],
        [{ type: 'number' }, ''],
        [{ type: 'string' }, "''"],
        [{ type: 'callable' }, '<fn >'],
        [{ type: 'repr' }, ''],
        [{ type: 'error' }, '< error>'],
    ])('fills the gaps of a sparse %j with %s', async function(initial, expected) {
        const { wrapper } = await node_mount({ auto_expand: true, initial: initial });

        expect(wrapper.text()).toBe(expected);
    });
});

describe('ValueNode checks', function() {
    it.each([
        [
            { auto_expand: true, template_index: 1.5 },
            'TypeError: a template index must be an integer: 1.5',
        ],
        [
            { auto_expand: true, template_index: -1 },
            'RangeError: a template index must not be negative: -1',
        ],
        [{ auto_expand: true, path: 'x' }, 'TypeError: a value path must be a list: x'],
        [{ initial: { type: 5 } }, 'TypeError: a value type must be text: 5'],
        [
            { auto_expand: true, initial: { items: 'x', type: 'dict' } },
            'TypeError: value children must be a list: x',
        ],
        [
            { auto_expand: true, initial: { items: [], size: NaN, type: 'dict' } },
            'RangeError: a container size must be finite: NaN',
        ],
        [
            { auto_expand: true, initial: { items: [child_with(5)], type: 'dict' } },
            'TypeError: a path step must be a record, not number',
        ],
        [
            { auto_expand: true, initial: { items: [child_with(null)], type: 'dict' } },
            'TypeError: a path step must be a record, not null',
        ],
        [
            { auto_expand: true, initial: { items: [child_with({ name: 'a' })], type: 'dict' } },
            'TypeError: a path step kind must be text: undefined',
        ],
    ])('refuses %j', async function(props, message) {
        const reported = await node_reported(props);

        expect(reported).toContain(message);
    });
});
