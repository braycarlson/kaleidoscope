import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils';
import type { Component, ComponentPublicInstance } from 'vue';
import { ROWS_VISIBLE_MAX } from '../../../src/constants';
import { fetch_fake_create, settled, type FetchFake } from '../../support/fetch';
import { vue_reports } from '../../support/setup';

interface QueryRaw {
    alias: string;
    many: boolean;
    params: string | null;
    raw_sql: string;
    rows: number | null;
    sql: string;
    stack: { file: string; function: string; line: number; text: string }[];
    templates: { line: number; name: string; text: string }[];
    time: number;
}

interface RequestRaw {
    duration: number;
    is_ajax: boolean;
    method: string;
    path: string;
    queries: QueryRaw[];
    query_count: number;
    query_time: number;
    request_id: string;
    status_code: number;
    timestamp: number;
}

const SQL_AUTHOR = 'SELECT * FROM author';
const SQL_BOOK = 'SELECT * FROM book WHERE id = 1';
const SQL_UPDATE = 'UPDATE book SET title = 2';

function query_build(sql: string, time: number): QueryRaw {
    const frame = {
        file: '/app/views.py',
        function: 'index',
        line: 12,
        text: 'Book.objects.get()',
    };

    return {
        alias: 'default',
        many: false,
        params: '(1,)',
        raw_sql: sql,
        rows: 1,
        sql: sql,
        stack: [frame],
        templates: [],
        time: time,
    };
}

function requests_build(): RequestRaw[] {
    const page: RequestRaw = {
        duration: 30,
        is_ajax: false,
        method: 'GET',
        path: '/books/',
        queries: [
            query_build(SQL_BOOK, 0.002),
            query_build(SQL_BOOK, 0.004),
            query_build(SQL_AUTHOR, 0.02),
        ],
        query_count: 3,
        query_time: 26,
        request_id: 'page',
        status_code: 200,
        timestamp: 1,
    };

    const ajax: RequestRaw = {
        duration: 4,
        is_ajax: true,
        method: 'POST',
        path: '/api/save/',
        queries: [query_build(SQL_UPDATE, 0.001)],
        query_count: 1,
        query_time: 1,
        request_id: 'ajax',
        status_code: 500,
        timestamp: 2,
    };

    return [ajax, page];
}

function data_build(requests: RequestRaw[] = requests_build()) {
    return {
        duplicates: { [SQL_BOOK]: 2 },
        requests: requests,
        similar: {
            'SELECT * FROM book WHERE id = %s': { count: 2, example: SQL_BOOK, total_time: 6 },
            'SELECT * FROM author WHERE id = %s': { count: 3, example: SQL_AUTHOR, total_time: 9 },
        },
        summary: { request_count: requests.length, total_queries: 4, total_query_time: 27 },
        track_ajax: true,
        track_page: true,
    };
}

async function panel_mount(data = data_build()): Promise<{ fake: FetchFake; wrapper: VueWrapper }> {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../../src/components/panels/QueriesPanel.vue');
    const wrapper = mount(module.default as Component, { props: { data: data } }) as VueWrapper;

    await flushPromises();

    return { fake, wrapper };
}

function request_rows(wrapper: VueWrapper): DOMWrapper<Element>[] {
    return wrapper.findAll('table.table-fixed > tbody > tr.cursor-pointer');
}

function texts_of(rows: DOMWrapper<Element>[], index: number): string[] {
    return rows.map(function(row) {
        return row.findAll('td')[index]?.text() ?? '';
    });
}

function cell_with_text(wrapper: VueWrapper, text: string): DOMWrapper<Element> {
    const cell = wrapper.findAll('td').find(function(candidate) {
        return candidate.find('span.font-mono').exists() && candidate.text() === text;
    });

    if (cell === undefined) throw new Error('no cell shows ' + text);

    return cell;
}

function toggle_named(wrapper: VueWrapper, label: string): DOMWrapper<Element> {
    const toggle = wrapper.findAll('div.cursor-pointer').find(function(candidate) {
        return candidate.text() === label;
    });

    if (toggle === undefined) throw new Error('no toggle is named ' + label);

    return toggle;
}

describe('QueriesPanel requests', function() {
    it('lists the slowest request first with its kind, status, and duplicates', async function() {
        const { wrapper } = await panel_mount();
        const rows = request_rows(wrapper);
        const header = wrapper.text();

        expect(texts_of(rows, 1)).toEqual(['PAGE', 'AJAX']);
        expect(texts_of(rows, 3)).toEqual(['/books/', '/api/save/']);
        expect(texts_of(rows, 4)).toEqual(['200', '500']);
        expect(texts_of(rows, 8)).toEqual(['2', '']);
        expect(header).toContain('Duplicates1');
        expect(header).toContain('Similar Groups2');
    });

    it('sorts the requests by any column in both directions', async function() {
        const { wrapper } = await panel_mount();
        const method = wrapper.findAllComponents({ name: 'SortHeader' }).find(function(header) {
            return header.props('column') === 'method';
        });

        if (method === undefined) throw new Error('no method column');

        await method.trigger('click');

        expect(texts_of(request_rows(wrapper), 2)).toEqual(['GET', 'POST']);

        await method.trigger('click');

        expect(texts_of(request_rows(wrapper), 2)).toEqual(['POST', 'GET']);
    });

    it('filters the requests by path, method, or statement', async function() {
        const { wrapper } = await panel_mount();
        const input = wrapper.findAll('input').at(0);

        if (input === undefined) throw new Error('no request filter');

        await input.setValue('UPDATE');

        expect(texts_of(request_rows(wrapper), 3)).toEqual(['/api/save/']);

        await input.setValue('get');

        expect(texts_of(request_rows(wrapper), 3)).toEqual(['/books/']);

        await input.setValue('nothing matches');

        expect(request_rows(wrapper)).toEqual([]);
    });

    it('says so when no request was captured', async function() {
        const { wrapper } = await panel_mount(data_build([]));

        expect(wrapper.text()).toContain('No requests captured');
    });
});

describe('QueriesPanel statement groups', function() {
    it('groups identical statements and expands a group into its occurrences', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const sql_cells = wrapper.findAll('td span.font-mono.block').map(function(span) {
            return span.text();
        });

        expect(sql_cells).toEqual([SQL_AUTHOR, SQL_BOOK]);

        const badge = wrapper.findAll('span').find(function(span) { return span.text() === '×2'; });

        await badge?.trigger('click');

        const occurrences = wrapper.findAll('td span.font-mono.block').map(function(span) {
            return span.text();
        });

        expect(occurrences).toEqual([SQL_AUTHOR, SQL_BOOK, SQL_BOOK, SQL_BOOK]);
    });

    it('sorts the statements of a request by time in both directions', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const time = wrapper.findAllComponents({ name: 'SortHeader' }).find(function(header) {
            return header.props('column') === 'time_ms';
        });

        if (time === undefined) throw new Error('no statement time column');

        await time.trigger('click');

        const ascending = wrapper.findAll('td span.font-mono.block').map(function(span) {
            return span.text();
        });

        await time.trigger('click');

        const descending = wrapper.findAll('td span.font-mono.block').map(function(span) {
            return span.text();
        });

        expect(ascending).toEqual([SQL_BOOK, SQL_AUTHOR]);
        expect(descending).toEqual([SQL_AUTHOR, SQL_BOOK]);
    });
});

function request_many(sql_for: (index: number) => string, count: number): RequestRaw {
    const queries = Array.from({ length: count }, function(_unused, index) {
        return query_build(sql_for(index), 0.001);
    });

    return {
        duration: 30,
        is_ajax: false,
        method: 'GET',
        path: '/many/',
        queries: queries,
        query_count: count,
        query_time: count,
        request_id: 'many',
        status_code: 200,
        timestamp: 3,
    };
}

function request_holding(queries: QueryRaw[]): RequestRaw {
    return {
        duration: 30,
        is_ajax: false,
        method: 'GET',
        path: '/held/',
        queries: queries,
        query_count: queries.length,
        query_time: queries.length,
        request_id: 'held',
        status_code: 200,
        timestamp: 4,
    };
}

function more_colspan(wrapper: VueWrapper): string {
    const cell = wrapper.get('[data-ks="rows-more"]').element.closest('td');

    if (cell === null) throw new Error('the more button sits in no cell');

    return cell.getAttribute('colspan') ?? '';
}

function sql_texts(wrapper: VueWrapper): string[] {
    return wrapper.findAll('td span.font-mono.block').map(function(span) {
        return span.text();
    });
}

function sql_rows_count(wrapper: VueWrapper): number {
    return wrapper.findAll('td span.font-mono.block').length;
}

describe('QueriesPanel long requests', function() {
    it('shows the first statements of a long request and the rest on request', async function() {
        const count = ROWS_VISIBLE_MAX + 50;
        const request = request_many(function(index) { return 'SELECT ' + index; }, count);
        const { wrapper } = await panel_mount(data_build([request]));

        await request_rows(wrapper)[0]?.trigger('click');

        expect(sql_rows_count(wrapper)).toBe(ROWS_VISIBLE_MAX);
        expect(wrapper.get('[data-ks="rows-more"]').text()).toBe('Show 50 more');

        await wrapper.get('[data-ks="rows-more"]').trigger('click');

        expect(sql_rows_count(wrapper)).toBe(ROWS_VISIBLE_MAX + 50);
        expect(wrapper.find('[data-ks="rows-more"]').exists()).toBe(false);
    });

    it('shows the first occurrences of a long group and the rest on request', async function() {
        const request = request_many(function() { return SQL_BOOK; }, ROWS_VISIBLE_MAX + 20);
        const { wrapper } = await panel_mount(data_build([request]));

        await request_rows(wrapper)[0]?.trigger('click');

        const badge = wrapper.findAll('span').find(function(span) {
            return span.text() === '×' + (ROWS_VISIBLE_MAX + 20);
        });

        await badge?.trigger('click');

        expect(sql_rows_count(wrapper)).toBe(ROWS_VISIBLE_MAX + 1);
        expect(wrapper.get('[data-ks="rows-more"]').text()).toBe('Show 20 more');

        await wrapper.get('[data-ks="rows-more"]').trigger('click');

        expect(sql_rows_count(wrapper)).toBe(ROWS_VISIBLE_MAX + 21);
    });
});

describe('QueriesPanel statement detail', function() {
    it('opens a statement in detail and closes it again', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');
        await cell_with_text(wrapper, SQL_BOOK).trigger('click');

        expect(wrapper.text()).toContain('Query #');
        expect(wrapper.text()).toContain('Duplicates2');

        await wrapper.get('button[aria-label="Close the query"]').trigger('click');

        expect(wrapper.text()).not.toContain('Query #');
    });

    it('copies the statements of a request as a numbered list', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const copy = wrapper.findAllComponents({ name: 'CopyButton' }).find(function(button) {
            return String(button.props('value')).startsWith('GET /books/');
        });

        expect(copy?.props('value')).toBe(
            'GET /books/\n3 queries, 26 ms total\n\n'
            + '1. (2.0 ms) ' + SQL_BOOK + '\n'
            + '2. (4.0 ms) ' + SQL_BOOK + '\n'
            + '3. (20.0 ms) ' + SQL_AUTHOR,
        );
    });

    it('filters the similar groups by their example statement', async function() {
        const { wrapper } = await panel_mount();
        const input = wrapper.findAll('input').at(1);

        if (input === undefined) throw new Error('no similar filter');

        await input.setValue('author');

        const rows = wrapper.findAll('tbody tr');

        expect(wrapper.text()).toContain(SQL_AUTHOR);
        expect(rows.some(function(row) { return row.text().includes('6.00 ms'); })).toBe(false);
    });
});

describe('QueriesPanel actions', function() {
    it('clears the store and asks for a refresh even when the server fails', async function() {
        const { fake, wrapper } = await panel_mount();

        await wrapper.get('button[aria-label="Clear the recorded requests"]').trigger('click');
        fake.take('/queries/action/clear/').fail('offline');
        await settled();

        expect(wrapper.emitted('refresh')).toHaveLength(1);
    });

    it('turns tracking off once the server agrees', async function() {
        const { fake, wrapper } = await panel_mount();

        await toggle_named(wrapper, 'Page').trigger('click');
        fake.take('/track-page-off/').resolve(200, { track_page: false });
        await settled();
        await toggle_named(wrapper, 'AJAX').trigger('click');
        fake.take('/track-ajax-off/').resolve(200, { track_ajax: false });
        await settled();

        expect(toggle_named(wrapper, 'Page').find('span').classes()).toContain('opacity-40');
        expect(toggle_named(wrapper, 'AJAX').find('span').classes()).toContain('opacity-40');
        expect(wrapper.emitted('refresh')).toBeUndefined();
    });

    it('asks for a refresh when the server refuses a tracking change', async function() {
        const { fake, wrapper } = await panel_mount();

        await toggle_named(wrapper, 'Page').trigger('click');
        fake.take('/track-page-off/').resolve(500, { error: 'refused' });
        await settled();
        await toggle_named(wrapper, 'AJAX').trigger('click');
        fake.take('/track-ajax-off/').resolve(500, { error: 'refused' });
        await settled();

        expect(wrapper.emitted('refresh')).toHaveLength(2);
        expect(toggle_named(wrapper, 'Page').find('span').classes()).not.toContain('opacity-40');
    });

    it('follows tracking that changed on the server', async function() {
        const { wrapper } = await panel_mount();
        const data = { ...data_build(), track_ajax: false, track_page: false };

        await wrapper.setProps({ data: data });

        expect(toggle_named(wrapper, 'Page').find('span').classes()).toContain('opacity-40');
        expect(toggle_named(wrapper, 'AJAX').find('span').classes()).toContain('opacity-40');
    });
});

function slow_requests(): RequestRaw[] {
    const queries = Array.from({ length: 12 }, function() { return query_build(SQL_BOOK, 0.015); });
    const query_bare = { ...query_build(SQL_AUTHOR, 0), alias: undefined } as unknown as QueryRaw;
    const request = requests_build()[1];

    if (request === undefined) throw new Error('no page request');

    return [{ ...request, queries: [...queries, query_bare], query_count: 13 }];
}

function data_slow() {
    return { ...data_build(slow_requests()), duplicates: { [SQL_BOOK]: 12 } };
}

describe('QueriesPanel statement cells', function() {
    it('opens a statement from its bar, its time, or its arrow', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const group_row = cell_with_text(wrapper, SQL_AUTHOR).element.parentElement;

        if (group_row === null) throw new Error('the statement has no row');

        const cells = Array.from(group_row.children);

        for (const index of [1, 2, 6]) {
            cells[index]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            await flushPromises();

            expect(wrapper.text()).toContain('Query #3');

            await wrapper.get('button[aria-label="Close the query"]').trigger('click');
        }
    });

    it('expands a group from its arrow cell but not a single statement', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const single = cell_with_text(wrapper, SQL_AUTHOR).element.parentElement?.children[0];
        const grouped = cell_with_text(wrapper, SQL_BOOK).element.parentElement?.children[0];

        single?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        grouped?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await flushPromises();

        expect(wrapper.findAll('td span.font-mono.block')).toHaveLength(4);
    });

    it('opens one occurrence of a group in detail', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const badge = wrapper.findAll('span').find(function(span) { return span.text() === '×2'; });

        await badge?.trigger('click');

        const occurrence = wrapper.findAll('tr.cursor-pointer').filter(function(row) {
            return row.text().includes(SQL_BOOK);
        }).at(-1);

        await occurrence?.trigger('click');

        expect(wrapper.text()).toMatch(/Query #[12]/);
    });
});

describe('QueriesPanel statement marks', function() {
    it('flags slow statements, many duplicates, and a missing alias', async function() {
        const { wrapper } = await panel_mount(data_slow());

        await request_rows(wrapper)[0]?.trigger('click');

        const badge = wrapper.findAll('span').find(function(span) {
            return span.text() === '×12';
        });

        await badge?.trigger('click');

        expect(request_rows(wrapper)[0]?.findAll('td')[8]?.classes()).toContain('text-orange-500');
        expect(wrapper.findAll('td.text-orange-500').length).toBeGreaterThan(1);

        await cell_with_text(wrapper, SQL_AUTHOR).trigger('click');

        expect(wrapper.text()).not.toContain('Database');
    });

    it('draws bars for statements that all took no time', async function() {
        const zero = requests_build().map(function(request) {
            const queries = request.queries.map(function(query) { return { ...query, time: 0 }; });

            return { ...request, queries: queries };
        });

        const { wrapper } = await panel_mount(data_build(zero));

        await request_rows(wrapper)[0]?.trigger('click');

        const bar = wrapper.find('div.h-full.rounded-full');

        expect(bar.attributes('style')).toContain('width: 2%');
    });
});

describe('QueriesPanel statement sort columns', function() {
    it('sorts the statements by any known column the header names', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const time = wrapper.findAllComponents({ name: 'SortHeader' }).find(function(header) {
            return header.props('column') === 'time_ms';
        });

        if (time === undefined) throw new Error('no statement time column');

        const header = time.vm as ComponentPublicInstance;

        header.$emit('sort', 'sql');
        await flushPromises();

        const by_sql = wrapper.findAll('td span.font-mono.block').map(function(span) {
            return span.text();
        });

        header.$emit('sort', 'index');
        await flushPromises();

        const by_index = wrapper.findAll('td span.font-mono.block').map(function(span) {
            return span.text();
        });

        expect(by_sql).toEqual([SQL_AUTHOR, SQL_BOOK]);
        expect(by_index).toEqual([SQL_BOOK, SQL_AUTHOR]);
    });
});

describe('QueriesPanel rows and template lines', function() {
    it('shows the rows of each statement and the template line that issued it', async function() {
        const templated = {
            ...query_build(SQL_AUTHOR, 0.02),
            rows: 60,
            templates: [
                { line: 1, name: 'page/book_list.html', text: '{% for book in books %}' },
                { line: 3, name: 'partial/book_row.html', text: '{{ book.author.name }}' },
            ],
        };

        const unknown = { ...query_build(SQL_BOOK, 0.001), rows: null };
        const { wrapper } = await panel_mount(data_build([request_holding([templated, unknown])]));

        await request_rows(wrapper)[0]?.trigger('click');

        const rows = wrapper.findAll('[data-ks="query-rows"]').map(function(cell) {
            return cell.text();
        });

        const locations = wrapper.findAll('[data-ks="query-template"]').map(function(line) {
            return line.text();
        });

        expect(rows).toEqual(['60', '']);
        expect(locations).toEqual(['partial/book_row.html:3 {{ book.author.name }}']);
    });

});

describe('QueriesPanel without known rows', function() {
    it('leaves the rows column out for a database that reports no rows', async function() {
        const unknown = [{ ...query_build(SQL_AUTHOR, 0.02), rows: null }];
        const { wrapper } = await panel_mount(data_build([request_holding(unknown)]));

        await request_rows(wrapper)[0]?.trigger('click');

        const headers = wrapper.findAllComponents({ name: 'SortHeader' }).map(function(header) {
            return header.props('column') as string;
        });

        expect(headers).not.toContain('rows');
        expect(wrapper.findAll('[data-ks="query-rows"]')).toHaveLength(0);
    });

    it('spans one column fewer in long lists without known rows', async function() {
        const count = ROWS_VISIBLE_MAX + 5;

        const distinct = Array.from({ length: count }, function(_unused, index) {
            return { ...query_build('SELECT ' + index, 0.001), rows: null };
        });

        const repeated = Array.from({ length: count }, function() {
            return { ...query_build(SQL_BOOK, 0.001), rows: null };
        });

        const { wrapper } = await panel_mount(data_build([request_holding(distinct)]));

        await request_rows(wrapper)[0]?.trigger('click');

        const spans_groups = more_colspan(wrapper);

        await wrapper.setProps({ data: data_build([request_holding(repeated)]) });

        const badge = wrapper.findAll('span').find(function(span) {
            return span.text() === '×' + count;
        });

        await badge?.trigger('click');

        const spans_occurrences = more_colspan(wrapper);

        expect(spans_groups).toBe('6');
        expect(spans_occurrences).toBe('6');
        expect(wrapper.findAll('[data-ks="query-rows"]')).toHaveLength(0);
    });

});

describe('QueriesPanel row sorting and template lines', function() {
    it('sorts the statements of a request by their rows in both directions', async function() {
        const few = { ...query_build(SQL_AUTHOR, 0.02), rows: 5 };
        const many = { ...query_build(SQL_BOOK, 0.001), rows: 900 };
        const { wrapper } = await panel_mount(data_build([request_holding([few, many])]));

        await request_rows(wrapper)[0]?.trigger('click');

        const header = wrapper.findAllComponents({ name: 'SortHeader' }).find(function(candidate) {
            return candidate.props('column') === 'rows';
        });

        if (header === undefined) throw new Error('no statement rows column');

        await header.trigger('click');

        const ascending = sql_texts(wrapper);

        await header.trigger('click');

        const descending = sql_texts(wrapper);

        expect(ascending).toEqual([SQL_AUTHOR, SQL_BOOK]);
        expect(descending).toEqual([SQL_BOOK, SQL_AUTHOR]);
    });

    it('opens a statement with the request it belongs to', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');
        await cell_with_text(wrapper, SQL_BOOK).trigger('click');

        const detail = wrapper.findComponent({ name: 'QueryDetail' });
        const query = detail.props('query') as { request_id: string };

        expect(query.request_id).toBe('page');
    });
});

describe('QueriesPanel checks', function() {
    it('refuses to draw a bar for a time that is not finite', async function() {
        const request = request_many(function() { return SQL_BOOK; }, 1);
        const query = request.queries[0];

        if (query === undefined) throw new Error('the request carries no query');

        query.time = NaN;

        const { wrapper } = await panel_mount(data_build([request]));

        await request_rows(wrapper)[0]?.trigger('click');

        const reports = vue_reports.splice(0).join('\n');

        expect(reports).toContain('RangeError: a bar needs a finite time in ms: NaN');
    });

    it('refuses to show a row count that is not finite', async function() {
        const broken = { ...query_build(SQL_BOOK, 0.001), rows: NaN };
        const { wrapper } = await panel_mount(data_build([request_holding([broken])]));

        await request_rows(wrapper)[0]?.trigger('click');

        const reports = vue_reports.splice(0).join('\n');

        expect(reports).toContain('RangeError: a row count must be finite: NaN');
    });

    it('refuses template lines that are not a list', async function() {
        const broken = { ...query_build(SQL_BOOK, 0.001), templates: 'x' as unknown as [] };
        const { wrapper } = await panel_mount(data_build([request_holding([broken])]));

        await request_rows(wrapper)[0]?.trigger('click');

        const reports = vue_reports.splice(0).join('\n');

        expect(reports).toContain('TypeError: template frames must be a list: x');
    });

    it('refuses to sort the statements by an unknown column', async function() {
        const { wrapper } = await panel_mount();

        await request_rows(wrapper)[0]?.trigger('click');

        const time = wrapper.findAllComponents({ name: 'SortHeader' }).find(function(header) {
            return header.props('column') === 'time_ms';
        });

        if (time === undefined) throw new Error('no statement time column');

        const header = time.vm as ComponentPublicInstance;

        header.$emit('sort', 'bogus');
        await flushPromises();

        const reports = vue_reports.splice(0).join('\n');

        expect(reports).toContain('RangeError: queries cannot be sorted by bogus');
    });
});
