import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import { fetch_fake_create, type FetchFake } from '../../support/fetch';
import { vue_reports } from '../../support/setup';

interface TemplateShown {
    context_keys?: string[];
    duration_ms: number;
    name: string;
}

const TEMPLATES = Object.freeze([
    { context_keys: ['book', 'title'], duration_ms: 12.5, name: 'books/list.html' },
    { duration_ms: 6, name: '<inline>' },
    { context_keys: [], duration_ms: 1, name: 'books/row.html' },
]);

function data_build(templates: TemplateShown[] = [...TEMPLATES]) {
    return { count: templates.length, templates: templates, total_time: 19.5 };
}

async function panel_mount(data = data_build()): Promise<{ fake: FetchFake; wrapper: VueWrapper }> {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../../src/components/panels/TemplatesPanel.vue');
    const wrapper = mount(module.default as Component, { props: { data: data } }) as VueWrapper;

    await flushPromises();

    return { fake, wrapper };
}

async function mount_reported(templates: unknown[]): Promise<string> {
    let thrown = '';

    try {
        await panel_mount(data_build(templates as TemplateShown[]));
    } catch (error: unknown) {
        thrown = String(error);
    }

    return [thrown, ...vue_reports.splice(0)].join('\n');
}

function names_listed(wrapper: VueWrapper): string[] {
    const cells = wrapper.findAll('tbody tr td:first-child span');

    return cells.map(function(cell) { return cell.text(); });
}

function header_named(wrapper: VueWrapper, label: string) {
    const header = wrapper.findAll('th').find(function(cell) { return cell.text() === label; });

    if (header === undefined) throw new Error('no header is named ' + label);

    return header;
}

function row_named(wrapper: VueWrapper, name: string) {
    const row = wrapper.findAll('tbody tr').find(function(candidate) {
        return candidate.find('td span').text() === name;
    });

    if (row === undefined) throw new Error('no row is named ' + name);

    return row;
}

describe('TemplatesPanel listing', function() {
    it('lists the slowest template first and marks the slow and the inline ones', async function() {
        const { wrapper } = await panel_mount();
        const durations = wrapper.findAll('tbody tr td:nth-child(2) span');

        expect(names_listed(wrapper)).toEqual(['books/list.html', '<inline>', 'books/row.html']);
        expect(durations.map(function(cell) { return cell.classes().join(' '); })).toEqual([
            'text-orange-500 font-semibold',
            'text-yellow-500',
            '',
        ]);
        expect(wrapper.find('tbody tr td span.italic').text()).toBe('<inline>');
    });

    it('sorts by any column in both directions', async function() {
        const { wrapper } = await panel_mount();

        await header_named(wrapper, 'Template').trigger('click');

        const ascending = names_listed(wrapper);

        await header_named(wrapper, 'Template').trigger('click');

        expect(ascending).toEqual(['<inline>', 'books/list.html', 'books/row.html']);
        expect(names_listed(wrapper)).toEqual(['books/row.html', 'books/list.html', '<inline>']);
    });

    it('filters the templates by name', async function() {
        const { wrapper } = await panel_mount();

        await wrapper.get('input').setValue('ROW');

        expect(names_listed(wrapper)).toEqual(['books/row.html']);
    });
});

describe('TemplatesPanel context', function() {
    it('expands a template into its context keys and reads the chosen one', async function() {
        const { fake, wrapper } = await panel_mount();

        await row_named(wrapper, 'books/list.html').trigger('click');

        const keys = wrapper.findAll('button.font-mono');

        expect(keys.map(function(key) { return key.text(); })).toEqual(['book', 'title']);

        await keys[1]?.trigger('click');
        await flushPromises();

        expect(fake.take('/templates/action/value/').url).toContain('template=0');

        await keys[1]?.trigger('click');
        await flushPromises();

        expect(fake.pending).toEqual([]);
        expect(wrapper.findAllComponents({ name: 'ValueNode' })).toEqual([]);
    });

    it('says so when a template has no context and when none rendered', async function() {
        const { wrapper } = await panel_mount();

        await row_named(wrapper, '<inline>').trigger('click');

        expect(wrapper.text()).toContain('No context variables');

        await wrapper.setProps({ data: data_build([]) });

        expect(wrapper.text()).toContain('No templates rendered');
    });

    it('forgets the chosen keys once another page rendered', async function() {
        const { wrapper } = await panel_mount();

        await row_named(wrapper, 'books/list.html').trigger('click');
        await wrapper.findAll('button.font-mono')[0]?.trigger('click');
        await flushPromises();

        const templates = [{ context_keys: ['book'], duration_ms: 2, name: 'other.html' }];

        await wrapper.setProps({ data: data_build(templates) });
        await row_named(wrapper, 'other.html').trigger('click');

        expect(wrapper.find('button.font-mono').classes()).not.toContain('text-purple-200');
    });
});

describe('TemplatesPanel without templates', function() {
    it('says so when the data carries no template list', async function() {
        const { wrapper } = await panel_mount({} as ReturnType<typeof data_build>);

        expect(wrapper.text()).toContain('No templates rendered');
        expect(wrapper.text()).toContain('Templates0');
    });
});

describe('TemplatesPanel checks', function() {
    it.each([
        [
            { context_keys: [], duration_ms: 1, name: 5 },
            'TypeError: a template name must be text: 5',
        ],
        [
            { context_keys: [], duration_ms: NaN, name: 'a.html' },
            'RangeError: a template duration must be a finite number: NaN',
        ],
        [
            { context_keys: 'abc', duration_ms: 1, name: 'a.html' },
            'TypeError: context keys must be a list: abc',
        ],
    ])('refuses the template %j', async function(template, message) {
        const reported = await mount_reported([template]);

        expect(reported).toContain(message);
    });

    it('refuses a context key that is not text', async function() {
        const templates = [{ context_keys: [5], duration_ms: 1, name: 'a.html' }];
        const { wrapper } = await panel_mount(data_build(templates as unknown as TemplateShown[]));

        await row_named(wrapper, 'a.html').trigger('click');
        await wrapper.get('button.font-mono').trigger('click');

        const reports = vue_reports.splice(0).join('\n');

        expect(reports).toContain('TypeError: a context key must be text: 5');
    });
});
