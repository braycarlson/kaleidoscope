import { describe, expect, it } from 'vitest';
import { mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import CachePanel from '../../../src/components/panels/CachePanel.vue';
import LineProfilerPanel from '../../../src/components/panels/LineProfilerPanel.vue';
import MemoryPanel from '../../../src/components/panels/MemoryPanel.vue';
import PrismCode from '../../../src/components/panels/PrismCode.vue';
import ProfilingPanel from '../../../src/components/panels/ProfilingPanel.vue';
import RequestPanel from '../../../src/components/panels/RequestPanel.vue';
import SettingsPanel from '../../../src/components/panels/SettingsPanel.vue';
import SignalsPanel from '../../../src/components/panels/SignalsPanel.vue';
import StaticFilesPanel from '../../../src/components/panels/StaticFilesPanel.vue';
import TimerPanel from '../../../src/components/panels/TimerPanel.vue';
import VersionsPanel from '../../../src/components/panels/VersionsPanel.vue';
import { ROWS_VISIBLE_MAX } from '../../../src/constants';
import { vue_reports } from '../../support/setup';

interface CheckCase {
    component: Component;
    message: string;
    name: string;
    props: Record<string, unknown>;
}

function element_named(wrapper: VueWrapper, selector: string, text: string): DOMWrapper<Element> {
    const element = wrapper.findAll(selector).find(function(candidate) {
        return candidate.text().startsWith(text);
    });

    if (element === undefined) throw new Error('no ' + selector + ' reads ' + text);

    return element;
}

function cache_call(method: string, hit: boolean, args: string) {
    return { alias: 'default', args: args, duration_ms: 0.5, hit: hit, method: method };
}

function memory_row(type: string, count: number, size: number, category: string) {
    return { category: category, count: count, size: size, size_display: size + ' B', type: type };
}

function cache_data(call: Record<string, unknown>) {
    const merged = { ...cache_call('GET', true, "'a'"), ...call };

    return { calls: [merged], count: 1, hits: 0, misses: 0, total_time: 1 };
}

function line_data(pct: unknown) {
    const line = { hits: 1, lineno: 1, pct: pct, per_hit_ms: 1, source: 'x', time_ms: 1 };

    const function_entry = {
        filename: 'views.py',
        full_path: '/app/views.py',
        func_name: 'index',
        lines: [line],
        start_lineno: 1,
        total_time_ms: 1,
    };

    return { duration_ms: 1, function_count: 1, functions: [function_entry], has_data: true };
}

function memory_data(row: Record<string, unknown>) {
    const merged = { ...memory_row('dict', 1, 64, 'builtin'), ...row };

    return { diff: [merged], total_objects: 1, total_size: 64, total_size_display: '64 B' };
}

function signals_data(signal: Record<string, unknown>) {
    const merged = {
        module: 'django',
        name: 'post_save',
        receiver_count: 0,
        receivers: [],
        ...signal,
    };

    return {
        count: 1,
        send_count: 0,
        send_time: 0,
        sends: [],
        signals: [merged],
        total_receivers: 0,
    };
}

function reported_by(component: Component, props: Record<string, unknown>): string {
    let thrown = '';

    try {
        mount(component, { props: props }).unmount();
    } catch (error: unknown) {
        thrown = String(error);
    }

    return [thrown, ...vue_reports.splice(0)].join('\n');
}

function texts_of(cells: DOMWrapper<Element>[]): string[] {
    return cells.map(function(cell) { return cell.text(); });
}

function classes_of(cells: DOMWrapper<Element>[]): string[] {
    return cells.map(function(cell) { return cell.classes().join(' '); });
}

function count_containing(texts: string[], part: string): number {
    return texts.filter(function(text) { return text.includes(part); }).length;
}

describe('CachePanel details', function() {
    it('colors each method by what it does and marks writes as having no result', function() {
        const calls = [
            cache_call('GET', true, "'a'"),
            cache_call('SET', false, "'a', 1"),
            cache_call('DELETE', false, "'a'"),
            cache_call('INCR', false, "'n'"),
            cache_call('TOUCH', false, "'t'"),
        ];

        const data = { calls: calls, count: 5, hits: 1, misses: 0, total_time: 2.5 };
        const wrapper = mount(CachePanel, { props: { data: data } }) as VueWrapper;
        const methods = wrapper.findAll('tbody tr td:nth-child(2) span');
        const results = wrapper.findAll('tbody tr td:nth-child(4)');

        expect(classes_of(methods)).toEqual([
            'text-blue-400',
            'text-green-400',
            'text-red-400',
            'text-yellow-400',
            '',
        ]);
        expect(texts_of(results)).toEqual(['Hit', '-', '-', '-', 'Miss']);
    });

    it('filters the calls by method, alias, or arguments', async function() {
        const calls = [cache_call('GET', true, "'user:1'"), cache_call('SET', false, "'page'")];
        const data = { calls: calls, count: 2, hits: 1, misses: 0, total_time: 1 };
        const wrapper = mount(CachePanel, { props: { data: data } }) as VueWrapper;

        await wrapper.get('input').setValue('USER');

        expect(wrapper.findAll('tbody tr')).toHaveLength(1);
    });
});

describe('CachePanel rows', function() {
    it('shows the first calls of a long table and the rest on request', async function() {
        const calls = Array.from({ length: ROWS_VISIBLE_MAX + 5 }, function(_unused, index) {
            return cache_call('GET', true, "'key:" + index + "'");
        });

        const count = calls.length;
        const data = { calls: calls, count: count, hits: count, misses: 0, total_time: 1 };
        const wrapper = mount(CachePanel, { props: { data: data } }) as VueWrapper;

        expect(wrapper.findAll('tbody tr')).toHaveLength(ROWS_VISIBLE_MAX + 1);
        expect(wrapper.get('[data-ks="rows-more"]').text()).toBe('Show 5 more');

        await wrapper.get('[data-ks="rows-more"]').trigger('click');

        expect(wrapper.findAll('tbody tr')).toHaveLength(ROWS_VISIBLE_MAX + 5);
    });
});

describe('StaticFilesPanel rows', function() {
    it('shows the first files of a long list and the rest on request', async function() {
        const files = Array.from({ length: ROWS_VISIBLE_MAX + 3 }, function(_unused, index) {
            const path = String(index);

            return { finder: 'AppDirectoriesFinder', full_path: '/static/' + path, path: path };
        });

        const data = { all_count: files.length, all_files: files, used_count: 0, used_files: [] };
        const wrapper = mount(StaticFilesPanel, { props: { data: data } }) as VueWrapper;

        expect(wrapper.findAll('tbody tr td.font-mono')).toHaveLength(ROWS_VISIBLE_MAX);
        expect(wrapper.get('[data-ks="rows-more"]').text()).toBe('Show 3 more');

        await wrapper.get('[data-ks="rows-more"]').trigger('click');

        expect(wrapper.findAll('tbody tr td.font-mono')).toHaveLength(ROWS_VISIBLE_MAX + 3);
    });
});

describe('LineProfilerPanel details', function() {
    it('shades each line by its share of the time', function() {
        const lines = [50, 30, 15, 7, 1].map(function(pct, index) {
            return {
                hits: 1,
                lineno: index + 1,
                pct: pct,
                per_hit_ms: 1,
                source: 'line',
                time_ms: pct,
            };
        });

        const function_entry = {
            filename: 'views.py',
            full_path: '/app/views.py',
            func_name: 'index',
            lines: lines,
            start_lineno: 1,
            total_time_ms: 103,
        };

        const data = {
            duration_ms: 103,
            function_count: 1,
            functions: [function_entry],
            has_data: true,
        };

        const wrapper = mount(LineProfilerPanel, { props: { data: data } }) as VueWrapper;
        const rows = classes_of(wrapper.findAll('tbody tr'));

        expect(count_containing(rows, 'bg-ks-row-critical')).toBe(1);
        expect(count_containing(rows, 'bg-ks-row-high')).toBe(1);
        expect(count_containing(rows, 'bg-ks-row-medium')).toBe(1);
        expect(count_containing(rows, 'bg-ks-row-low')).toBe(1);
        expect(wrapper.findAll('td.text-red-400')).toHaveLength(1);
        expect(wrapper.findAll('td.text-orange-400')).toHaveLength(1);
        expect(wrapper.findAll('td.text-yellow-400')).toHaveLength(1);
    });

    it('explains how to profile when nothing was profiled', function() {
        const wrapper = mount(LineProfilerPanel, { props: { data: {} } }) as VueWrapper;

        expect(wrapper.text()).toContain('No line profile');
    });
});

const MEMORY_ROWS = Object.freeze([
    memory_row('builtins.dict', 4, 512, 'builtin'),
    memory_row('app.Book', -2, -64, 'project'),
    memory_row('django.Model', 0, 0, ''),
]);

const MEMORY_DATA = Object.freeze({
    diff: [...MEMORY_ROWS],
    total_objects: 1200,
    total_size: 4096,
    total_size_display: '4.0 KB',
});

function types_shown(wrapper: VueWrapper): string[] {
    return texts_of(wrapper.findAll('tbody tr td:first-child'));
}

describe('MemoryPanel rows', function() {
    const data = MEMORY_DATA;

    it('shows allocated and freed rows by default and colors them', function() {
        const wrapper = mount(MemoryPanel, { props: { data: data } }) as VueWrapper;

        expect(types_shown(wrapper)).toEqual(['builtins.dict', 'app.Book']);
        expect(wrapper.text()).toContain('Total Objects1,200');
        expect(wrapper.get('tbody tr td:first-child').classes()).toContain('text-red-400');
    });

    it('shows or hides each kind of row on request', async function() {
        const wrapper = mount(MemoryPanel, { props: { data: data } }) as VueWrapper;

        await element_named(wrapper, 'div.cursor-pointer', 'Unchanged').trigger('click');
        await element_named(wrapper, 'div.cursor-pointer', 'Allocated').trigger('click');

        expect(types_shown(wrapper)).toEqual(['django.Model', 'app.Book']);

        await element_named(wrapper, 'div.cursor-pointer', 'Freed').trigger('click');

        expect(types_shown(wrapper)).toEqual(['django.Model']);
    });
});

describe('MemoryPanel filters', function() {
    const data = MEMORY_DATA;

    it('narrows the rows to one category and back', async function() {
        const wrapper = mount(MemoryPanel, { props: { data: data } }) as VueWrapper;

        await element_named(wrapper, 'button', 'project').trigger('click');

        expect(types_shown(wrapper)).toEqual(['app.Book']);

        await element_named(wrapper, 'button', 'project').trigger('click');

        expect(types_shown(wrapper)).toEqual(['builtins.dict', 'app.Book']);
    });

    it('filters the rows by type', async function() {
        const wrapper = mount(MemoryPanel, { props: { data: data } }) as VueWrapper;

        await wrapper.get('input').setValue('BOOK');

        expect(types_shown(wrapper)).toEqual(['app.Book']);
    });

    it('explains how to capture memory when nothing was captured', function() {
        const wrapper = mount(MemoryPanel, { props: { data: {} } }) as VueWrapper;

        expect(wrapper.text()).toContain('No memory data captured yet');
    });
});

function settings_mount(settings: Record<string, unknown>): VueWrapper {
    const props = { data: { settings: settings } };

    return mount(SettingsPanel, { props: props }) as VueWrapper;
}

function previews(wrapper: VueWrapper): Record<string, string> {
    const shown: Record<string, string> = {};

    for (const row of wrapper.findAll('tbody tr')) {
        const cells = row.findAll('td');

        shown[cells[0]?.text() ?? ''] = cells[1]?.text() ?? '';
    }

    return shown;
}

describe('SettingsPanel details', function() {
    const long = 'x'.repeat(120);

    const settings = {
        DEBUG: true,
        EMPTY_DICT: {},
        EMPTY_LIST: [],
        INSTALLED_APPS: ['a', 'b'],
        LONG_TEXT: long,
        NOTHING: null,
        PORT: 8000,
        SECRET_KEY: '********',
        TEMPLATES: { BACKEND: 'django' },
    };

    it('previews every kind of value briefly', function() {
        const wrapper = settings_mount(settings);

        expect(previews(wrapper)).toEqual({
            DEBUG: 'True',
            EMPTY_DICT: '{}',
            EMPTY_LIST: '[]',
            INSTALLED_APPS: '[...]',
            LONG_TEXT: 'x'.repeat(77) + '...',
            NOTHING: 'None',
            PORT: '8000',
            SECRET_KEY: '********',
            TEMPLATES: '{...}',
        });
    });

    it('expands a long or nested value in full and folds it again', async function() {
        const wrapper = settings_mount(settings);
        const row = element_named(wrapper, 'tbody tr', 'TEMPLATES');

        await row.trigger('click');

        expect(row.find('pre').text()).toBe('{\n  "BACKEND": "django"\n}');

        await element_named(wrapper, 'tbody tr', 'LONG_TEXT').trigger('click');

        expect(element_named(wrapper, 'tbody tr', 'LONG_TEXT').find('pre').text()).toBe(long);

        await row.trigger('click');

        expect(row.find('pre').exists()).toBe(false);
    });

});

describe('SettingsPanel interaction', function() {
    const long = 'x'.repeat(120);

    const settings = {
        LONG_TEXT: long,
        PORT: 8000,
        TEMPLATES: { BACKEND: 'django' },
    };

    it('ignores a click on a value too short to expand', async function() {
        const wrapper = settings_mount(settings);
        const row = element_named(wrapper, 'tbody tr', 'PORT');

        await row.trigger('click');

        expect(row.find('pre').exists()).toBe(false);
    });

    it('filters the settings by name or value', async function() {
        const wrapper = settings_mount(settings);

        await wrapper.get('input').setValue('8000');

        expect(Object.keys(previews(wrapper))).toEqual(['PORT']);

        await wrapper.get('input').setValue('templ');

        expect(Object.keys(previews(wrapper))).toEqual(['TEMPLATES']);
    });
});

describe('TimerPanel details', function() {
    it('shows blanks for the fields a page did not report', function() {
        const wrapper = mount(TimerPanel, { props: { data: { total_ms: 5 } } }) as VueWrapper;
        const rows = wrapper.findAll('tbody tr').map(function(row) { return row.text(); });

        expect(rows).toEqual([
            'ServerWSGI',
            'Method',
            'Path',
            'Status Code',
            'Content Type',
            'Total Time5 ms',
        ]);
    });
});

describe('PrismCode details', function() {
    it('carries the alias classes of a token', function() {
        const code = '@property\ndef f():\n    """doc"""';
        const wrapper = mount(PrismCode, { props: { block: true, code: code } }) as VueWrapper;

        expect(wrapper.find('span.token.decorator.annotation.punctuation').exists()).toBe(true);
        expect(wrapper.find('span.token.triple-quoted-string.string').exists()).toBe(true);
    });
});

const CHECK_CASES: readonly CheckCase[] = Object.freeze([
    {
        component: CachePanel,
        message: 'TypeError: a cache method must be text: 7',
        name: 'a cache method that is not text',
        props: { data: cache_data({ method: 7 }) },
    },
    {
        component: CachePanel,
        message: 'RangeError: a cache call duration must be a finite number: NaN',
        name: 'a cache call duration that is not finite',
        props: { data: cache_data({ duration_ms: NaN }) },
    },
    {
        component: CachePanel,
        message: 'TypeError: a cache hit must be a bool: yes',
        name: 'a cache hit that is not a bool',
        props: { data: cache_data({ hit: 'yes' }) },
    },
    {
        component: CachePanel,
        message: 'TypeError: a cache key must be text: 7',
        name: 'a cache key that is not text',
        props: { data: cache_data({ args: 7 }) },
    },
    {
        component: LineProfilerPanel,
        message: 'RangeError: a line share must be a finite number: NaN',
        name: 'a line share that is not finite',
        props: { data: line_data(NaN) },
    },
    {
        component: MemoryPanel,
        message: 'RangeError: a memory row count must be a finite number: NaN',
        name: 'a memory row count that is not finite',
        props: { data: memory_data({ count: NaN }) },
    },
    {
        component: MemoryPanel,
        message: 'RangeError: a memory row size must be a finite number: NaN',
        name: 'a memory row size that is not finite',
        props: { data: memory_data({ size: NaN }) },
    },
    {
        component: MemoryPanel,
        message: 'TypeError: a memory category must be text: 5',
        name: 'a memory category that is not text',
        props: { data: memory_data({ category: 5 }) },
    },
    {
        component: PrismCode,
        message: 'TypeError: highlighted code must be text: 5',
        name: 'code to highlight that is not text',
        props: { code: 5 },
    },
    {
        component: ProfilingPanel,
        message: 'RangeError: a profile duration must be a finite number: NaN',
        name: 'a profile duration that is not finite',
        props: { data: { duration_ms: NaN, has_data: true, html: '', text: '' } },
    },
    {
        component: RequestPanel,
        message: 'TypeError: request data must be a record, not string',
        name: 'request headers that are text',
        props: { data: { headers: 'abc' } },
    },
    {
        component: RequestPanel,
        message: 'TypeError: request data must be a record, not a list',
        name: 'request parameters that are a list',
        props: { data: { get: ['a'] } },
    },
    {
        component: SettingsPanel,
        message: 'TypeError: the settings must be a record, not string',
        name: 'settings that are text',
        props: { data: { count: 0, settings: 'x' } },
    },
    {
        component: SettingsPanel,
        message: 'TypeError: the settings must be a record, not null',
        name: 'settings that are null',
        props: { data: { count: 0, settings: null } },
    },
    {
        component: SettingsPanel,
        message: 'TypeError: the settings must be a record, not a list',
        name: 'settings that are a list',
        props: { data: { count: 0, settings: [] } },
    },
    {
        component: SettingsPanel,
        message: 'TypeError: a setting is not JSON: function',
        name: 'a setting that has no JSON text',
        props: { data: { count: 1, settings: { HOOK: Math.max } } },
    },
    {
        component: SignalsPanel,
        message: 'TypeError: a signal name must be text: 5',
        name: 'a signal name that is not text',
        props: { data: signals_data({ name: 5 }) },
    },
    {
        component: SignalsPanel,
        message: 'RangeError: a receiver count must be finite: NaN',
        name: 'a receiver count that is not finite',
        props: { data: signals_data({ receiver_count: NaN }) },
    },
    {
        component: StaticFilesPanel,
        message: 'TypeError: a static path must be text: 5',
        name: 'a used static file that is not a path',
        props: { data: { all_count: 0, all_files: [], used_count: 1, used_files: [5] } },
    },
    {
        component: StaticFilesPanel,
        message: 'TypeError: a static file path must be text: 5',
        name: 'a static file whose path is not text',
        props: {
            data: { all_files: [{ finder: 'AppDirectoriesFinder', full_path: 5, path: 'a' }] },
        },
    },
    {
        component: TimerPanel,
        message: 'RangeError: a request time must be a finite number: NaN',
        name: 'a request time that is not finite',
        props: { data: { total_ms: NaN } },
    },
    {
        component: VersionsPanel,
        message: 'TypeError: a package description must be text: 5',
        name: 'a package description that is not text',
        props: {
            data: {
                count: 1,
                django: '6.1',
                packages: [{ description: 5, name: 'a', version: '1' }],
                python: '3.13',
            },
        },
    },
]);

describe('panel checks', function() {
    it.each(CHECK_CASES)('refuse $name', function(entry) {
        expect(reported_by(entry.component, entry.props)).toContain(entry.message);
    });
});
