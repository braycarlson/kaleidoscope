import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import { fetch_fake_create, settled, type FetchFake } from '../../support/fetch';
import { vue_reports } from '../../support/setup';

interface QueryShown {
    alias?: string;
    duplicate_count: number;
    many: boolean;
    params: string | null;
    raw_sql: string | null;
    request_id: string;
    rows: number | null;
    sql: string;
    stack: { file: string; function: string; line: number; text: string }[];
    templates: { line: number; name: string; text: string }[];
    time_ms: number;
}

interface Explaining {
    fake: FetchFake;
    wrapper: VueWrapper;
}

const SQL = 'select id from book where id = 1';

function query_build(overrides: Partial<QueryShown> = {}): QueryShown {
    return {
        duplicate_count: 0,
        many: false,
        params: null,
        raw_sql: null,
        request_id: 'request',
        rows: null,
        sql: SQL,
        stack: [],
        templates: [],
        time_ms: 1.25,
        ...overrides,
    };
}

async function detail_explaining(query: QueryShown): Promise<Explaining> {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../../src/components/panels/QueryDetail.vue');

    const wrapper = mount(module.default as Component, {
        props: { index: 2, query: query },
    }) as VueWrapper;

    await flushPromises();

    return { fake, wrapper };
}

async function detail_mount(
    query: QueryShown,
    duplicate_count: number,
    formatter_loaded: boolean,
): Promise<VueWrapper> {
    vi.resetModules();

    if (formatter_loaded) {
        const formatter = await import('../../../src/services/sql_formatter');

        await formatter.sql_formatter_preload();
    }

    const module = await import('../../../src/components/panels/QueryDetail.vue');

    return mount(module.default as Component, {
        props: { duplicate_count: duplicate_count, index: 2, query: query },
    }) as VueWrapper;
}

async function detail_reported(query: QueryShown, index: number): Promise<string> {
    vi.resetModules();

    const module = await import('../../../src/components/panels/QueryDetail.vue');
    let thrown = '';

    try {
        mount(module.default as Component, { props: { index: index, query: query } });
    } catch (error: unknown) {
        thrown = String(error);
    }

    return [thrown, ...vue_reports.splice(0)].join('\n');
}

function sections_of(wrapper: VueWrapper): string[] {
    return wrapper.findAllComponents({ name: 'CollapsibleSection' }).map(function(section) {
        return String(section.props('title'));
    });
}

describe('QueryDetail', function() {
    it('shows the duration and only the sections the query carries', async function() {
        const wrapper = await detail_mount(query_build(), 0, false);

        expect(wrapper.text()).toContain('Query #3');
        expect(wrapper.text()).toContain('Duration1.25 ms');
        expect(wrapper.text()).not.toContain('Rows');
        expect(sections_of(wrapper)).toEqual(['SQL', 'EXPLAIN']);
        expect(wrapper.find('pre').text()).toBe(SQL);
    });

    it('names a second database, executemany, and duplicates in its header', async function() {
        const query = query_build({ alias: 'replica', many: true });
        const wrapper = await detail_mount(query, 4, false);
        const header = wrapper.text();

        expect(header).toContain('Databasereplica');
        expect(header).toContain('Typeexecutemany');
        expect(header).toContain('Duplicates4');
    });

    it('shows raw SQL, parameters, the template lines, and every stack frame', async function() {
        const frames = [
            { file: '/app/views.py', function: 'index', line: 12, text: 'Book.objects.get()' },
            { file: '/app/models.py', function: 'save', line: 40, text: '' },
        ];

        const templates = [
            { line: 1, name: 'page/book_list.html', text: '{% for book in books %}' },
            { line: 3, name: 'partial/book_row.html', text: '' },
        ];

        const query = query_build({
            params: '(1,)',
            raw_sql: 'SELECT id FROM book WHERE id = %s',
            rows: 60,
            stack: frames,
            templates: templates,
        });

        const wrapper = await detail_mount(query, 0, false);

        expect(sections_of(wrapper)).toEqual([
            'SQL',
            'Raw SQL',
            'Parameters',
            'EXPLAIN',
            'Template',
            'Stack Trace',
        ]);
        expect(wrapper.text()).toContain('Rows60');
        expect(wrapper.text()).toContain('page/book_list.html:1');
        expect(wrapper.text()).toContain('{% for book in books %}');
        expect(wrapper.text()).toContain('partial/book_row.html:3');
        expect(wrapper.text()).toContain('/app/views.py:12');
        expect(wrapper.text()).toContain('Book.objects.get()');
    });

    it('offers no EXPLAIN for a write or for executemany', async function() {
        const write = query_build({ sql: 'UPDATE book SET title = 1' });
        const many = query_build({ many: true });
        const wrapper_write = await detail_mount(write, 0, false);
        const wrapper_many = await detail_mount(many, 0, false);

        expect(sections_of(wrapper_write)).toEqual(['SQL']);
        expect(sections_of(wrapper_many)).toEqual(['SQL']);
    });

});

describe('QueryDetail formatting', function() {
    it('formats the SQL once the formatter has loaded', async function() {
        const wrapper = await detail_mount(query_build({ raw_sql: SQL }), 0, true);
        const blocks = wrapper.findAll('pre').map(function(block) { return block.text(); });

        expect(blocks[0]).toContain('SELECT\n');
        expect(blocks[1]).toContain('SELECT\n');
    });

    it('leaves SQL too long or too broken to format as it is', async function() {
        const long = 'SELECT ' + 'x, '.repeat(8_000) + 'y';
        const broken = 'SELECT (((';
        const wrapper = await detail_mount(query_build({ raw_sql: broken, sql: long }), 0, true);
        const blocks = wrapper.findAll('pre').map(function(block) { return block.text(); });

        expect(blocks[0]).toBe(long);
        expect(blocks[1]).toBe(broken);
    });

    it('closes from its button and from the overlay', async function() {
        const wrapper = await detail_mount(query_build(), 0, false);

        await wrapper.get('button[aria-label="Close the query"]').trigger('click');
        await wrapper.get('div.bg-ks-overlay').trigger('click');

        expect(wrapper.emitted('close')).toHaveLength(2);
    });
});

describe('QueryDetail without a duplicate count', function() {
    it('leaves duplicates out of its header', async function() {
        vi.resetModules();

        const module = await import('../../../src/components/panels/QueryDetail.vue');
        const props = { index: 0, query: query_build() };
        const wrapper = mount(module.default as Component, { props: props }) as VueWrapper;

        expect(wrapper.text()).not.toContain('Duplicates');
    });
});

describe('QueryDetail checks', function() {
    it.each([
        [
            query_build({ sql: 5 as unknown as string }),
            0,
            'TypeError: the sql to format must be text: 5',
        ],
        [query_build(), 1.5, 'TypeError: a query index must be an integer: 1.5'],
        [query_build(), -1, 'RangeError: a query index must not be negative: -1'],
        [query_build({ time_ms: NaN }), 0, 'RangeError: a query time must be a finite number: NaN'],
        [query_build({ rows: NaN }), 0, 'RangeError: a row count must be finite: NaN'],
        [
            query_build({ templates: 'x' as unknown as [] }),
            0,
            'TypeError: template frames must be a list: x',
        ],
    ])('refuses the query %j at index %s', async function(query, index, message) {
        const reported = await detail_reported(query, index);

        expect(reported).toContain(message);
    });
});

describe('QueryDetail EXPLAIN', function() {
    it('runs EXPLAIN for its statement on request and shows the plan', async function() {
        const { fake, wrapper } = await detail_explaining(query_build({ request_id: 'page 1' }));

        await wrapper.get('[data-ks="explain"]').trigger('click');

        expect(wrapper.get('[data-ks="explain"]').text()).toBe('Explaining...');
        expect(wrapper.get('[data-ks="explain"]').attributes('disabled')).toBeDefined();

        const request = fake.take('/queries/action/explain/');
        const url = new URL(request.url, 'http://localhost');

        expect(url.searchParams.get('request')).toBe('page 1');
        expect(url.searchParams.get('query')).toBe('2');

        request.resolve(200, { command: 'EXPLAIN QUERY PLAN', plan: '2 0 0 SCAN book' });
        await settled();

        expect(wrapper.text()).toContain('EXPLAIN QUERY PLAN');
        expect(wrapper.findAll('pre.ks-code-block').at(-1)?.text()).toBe('2 0 0 SCAN book');
        expect(wrapper.find('[data-ks="explain"]').exists()).toBe(false);
    });

    it('shows the plan without a command when the server names none', async function() {
        const { fake, wrapper } = await detail_explaining(query_build());

        await wrapper.get('[data-ks="explain"]').trigger('click');
        fake.take('/explain/').resolve(200, { plan: 'Seq Scan on book' });
        await settled();

        expect(wrapper.text()).toContain('Seq Scan on book');
        expect(wrapper.find('div.text-ks-faint').exists()).toBe(false);
    });

    it('shows the reason the server refused and lets it be asked again', async function() {
        const { fake, wrapper } = await detail_explaining(query_build());

        await wrapper.get('[data-ks="explain"]').trigger('click');
        fake.take('/explain/').resolve(400, { error: 'only a SELECT can be explained' });
        await settled();

        expect(wrapper.text()).toContain('Error: only a SELECT can be explained');
        expect(wrapper.get('[data-ks="explain"]').text()).toBe('Run EXPLAIN');
    });

});

describe('QueryDetail EXPLAIN failures and stale answers', function() {
    it('shows the status when the server gives no plan and no reason', async function() {
        const { fake, wrapper } = await detail_explaining(query_build());

        await wrapper.get('[data-ks="explain"]').trigger('click');
        fake.take('/explain/').resolve(500, 'not json');
        await settled();

        expect(wrapper.text()).toContain('Error: HTTP 500');
    });

    it('shows a failure to reach the server', async function() {
        const { fake, wrapper } = await detail_explaining(query_build());

        await wrapper.get('[data-ks="explain"]').trigger('click');
        fake.take('/explain/').fail('Failed to fetch');
        await settled();

        expect(wrapper.text()).toContain('Error: TypeError: Failed to fetch');
    });

    it('forgets the plan once another statement opens', async function() {
        const { fake, wrapper } = await detail_explaining(query_build());

        await wrapper.get('[data-ks="explain"]').trigger('click');
        fake.take('/explain/').resolve(200, { command: 'EXPLAIN', plan: 'first plan' });
        await settled();
        await wrapper.setProps({ query: query_build({ sql: 'SELECT 2' }) });

        expect(wrapper.text()).not.toContain('first plan');
        expect(wrapper.get('[data-ks="explain"]').text()).toBe('Run EXPLAIN');
    });

    it('drops a plan or a failure that arrives after another statement opened', async function() {
        const { fake, wrapper } = await detail_explaining(query_build());

        await wrapper.get('[data-ks="explain"]').trigger('click');
        await wrapper.setProps({ query: query_build({ sql: 'SELECT 2' }) });
        fake.take('/explain/').resolve(200, { command: 'EXPLAIN', plan: 'stale plan' });
        await settled();
        await wrapper.get('[data-ks="explain"]').trigger('click');
        await wrapper.setProps({ query: query_build({ sql: 'SELECT 3' }) });
        fake.take('/explain/').fail('Failed to fetch');
        await settled();

        expect(wrapper.text()).not.toContain('stale plan');
        expect(wrapper.text()).not.toContain('Error');
        expect(wrapper.get('[data-ks="explain"]').text()).toBe('Run EXPLAIN');
    });

    it('refuses to explain a statement whose request has no id', async function() {
        const query = query_build({ request_id: 5 as unknown as string });
        const { wrapper } = await detail_explaining(query);

        await wrapper.get('[data-ks="explain"]').trigger('click');

        const reports = vue_reports.splice(0).join('\n');

        expect(reports).toContain('TypeError: a request id must be text: 5');
    });
});
