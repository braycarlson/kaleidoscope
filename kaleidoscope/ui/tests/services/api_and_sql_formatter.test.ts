import { describe, expect, it, vi } from 'vitest';
import { fetch_fake_create } from '../support/fetch';

const SQL_FORMATTED = 'SELECT\n    id\nFROM\n    book\nWHERE\n    id = 1';

async function api_load() {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../src/services/api');

    return { ...module, fake };
}

async function formatter_load() {
    vi.resetModules();

    return import('../../src/services/sql_formatter');
}

describe('json_fetch', function() {
    it('resolves the parsed body of a successful response', async function() {
        const { fake, json_fetch } = await api_load();
        const pending = json_fetch('/__kaleidoscope__/panels/');

        fake.take('/panels/').resolve(200, { panels: [] });

        await expect(pending).resolves.toEqual({ panels: [] });
    });

    it('rejects with the status of a failed response', async function() {
        const { fake, json_fetch } = await api_load();
        const pending = json_fetch('/__kaleidoscope__/panels/x/data/');

        fake.take('/data/').resolve(404, { error: 'missing' });

        await expect(pending).rejects.toThrow('HTTP 404: Error');
    });

    it('refuses an address outside the toolbar before fetching it', async function() {
        const { fake, json_fetch } = await api_load();

        expect(function() { return json_fetch('/api/books/'); }).toThrow(RangeError);
        expect(fake.calls).toEqual([]);
    });

    it('keeps the fetch it captured when the page later replaces fetch', async function() {
        const { fake, fetch_native } = await api_load();

        vi.stubGlobal('fetch', function() {
            throw new Error('the page replaced fetch');
        });

        const pending = fetch_native('/__kaleidoscope__/static/kaleidoscope.css');

        fake.take('kaleidoscope.css').resolve(200, '');

        await expect(pending).resolves.toBeInstanceOf(Response);
    });
});

describe('sql_formatter', function() {
    it('answers nothing until preloaded and then formats', async function() {
        const { sql_formatter_get, sql_formatter_preload } = await formatter_load();

        expect(sql_formatter_get()).toBeNull();

        const formatter = await sql_formatter_preload();

        expect(sql_formatter_get()).toBe(formatter);
        expect(formatter('select id from book where id = 1')).toBe(SQL_FORMATTED);
    });

    it('shares one preload between callers', async function() {
        const { sql_formatter_preload } = await formatter_load();

        expect(sql_formatter_preload()).toBe(sql_formatter_preload());
    });
});

describe('sql_formatter failures', function() {
    it('lets a failed preload be retried', async function() {
        vi.resetModules();
        vi.doMock('sql-formatter', function() {
            throw new Error('the formatter chunk failed to load');
        });

        const module = await import('../../src/services/sql_formatter');
        const first = module.sql_formatter_preload();

        await expect(first).rejects.toThrow();
        expect(module.sql_formatter_get()).toBeNull();

        const second = module.sql_formatter_preload();

        expect(second).not.toBe(first);
        await expect(second).rejects.toThrow();

        vi.doUnmock('sql-formatter');
    });
});
