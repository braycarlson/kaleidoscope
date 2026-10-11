import { describe, expect, it, vi } from 'vitest';
import { defineComponent, ref, type Component } from 'vue';
import { fetch_fake_create, settled } from '../support/fetch';

const DUMMY = defineComponent({ template: '<div />' });
const REGISTRY = Object.freeze({ queries: DUMMY, timer: DUMMY });

const PANELS = Object.freeze([
    { enabled: true, id: 'timer', isolate: false, summary: '12 ms', title: 'Timer' },
    { enabled: false, id: 'queries', isolate: false, summary: '0 queries', title: 'SQL Queries' },
]);

async function composable_load() {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../src/composables/use_panels');
    const disabled = ref<Record<string, boolean>>({});

    return { disabled, fake, panels: module.use_panels(REGISTRY, disabled) };
}

describe('use_panels data', function() {
    it('shows the data of the active panel and names its title and component', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        fake.take('/panels/timer/data/').resolve(200, { duration_ms: 4 });
        await settled();

        expect(panels.panel_data.value).toEqual({ duration_ms: 4 });
        expect(panels.component_active.value).toBe(DUMMY);
        expect(panels.title_panel.value).toBe('');
    });

    it('drops the data of a panel that is no longer active', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        panels.panel_active.value = 'queries';
        fake.take('/panels/timer/data/').resolve(200, { duration_ms: 4 });
        await settled();

        expect(panels.panel_data.value).toBeNull();
    });

    it('ignores an older response that arrives after a newer one', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        panels.panel_data_fetch('timer');

        const older = fake.take('/panels/timer/data/');
        const newer = fake.take('/panels/timer/data/');

        newer.resolve(200, { duration_ms: 2 });
        await settled();
        older.resolve(200, { duration_ms: 1 });
        await settled();

        expect(panels.panel_data.value).toEqual({ duration_ms: 2 });
    });
});

describe('use_panels data errors', function() {
    it('reports a failed data request instead of loading forever', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        fake.take('/panels/timer/data/').resolve(500, { error: 'broken' });
        await settled();

        expect(panels.panel_data.value).toBeNull();
        expect(panels.panel_error.value).toBe('HTTP 500: Error');
    });

    it('reports a network failure instead of rejecting unhandled', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        fake.take('/panels/timer/data/').fail('Failed to fetch');
        await settled();

        expect(panels.panel_error.value).toBe('Failed to fetch');
    });

    it('clears the error once a later request succeeds', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        fake.take('/panels/timer/data/').fail('Failed to fetch');
        await settled();
        panels.panel_data_fetch('timer');
        fake.take('/panels/timer/data/').resolve(200, { duration_ms: 9 });
        await settled();

        expect(panels.panel_error.value).toBeNull();
        expect(panels.panel_data.value).toEqual({ duration_ms: 9 });
    });
});

describe('use_panels metadata', function() {
    it('lists the panels and mirrors their enabled state from the server', async function() {
        const { disabled, fake, panels } = await composable_load();

        disabled.value = { timer: true, retired: true };

        const loaded = panels.panel_metadata_fetch();

        fake.take('/__kaleidoscope__/panels/').resolve(200, { panels: PANELS });
        await loaded;

        expect(panels.panels_available.value).toEqual(PANELS);
        expect(disabled.value).toEqual({ queries: true, retired: true, timer: false });

        panels.panel_active.value = 'queries';

        expect(panels.title_panel.value).toBe('SQL Queries');
    });

    it('ignores a stale panel list that arrives after a newer one', async function() {
        const { fake, panels } = await composable_load();
        const first = panels.panel_metadata_fetch();
        const second = panels.panel_metadata_fetch();
        const older = fake.take('/__kaleidoscope__/panels/');
        const newer = fake.take('/__kaleidoscope__/panels/');

        newer.resolve(200, { panels: PANELS });
        await second;
        older.resolve(200, { panels: [] });
        await first;

        expect(panels.panels_available.value).toEqual(PANELS);
    });

    it.each([
        ['an error status', 500, { error: 'broken' }],
        ['a body without panels', 200, { other: [] }],
        ['panels of the wrong shape', 200, { panels: [{ id: 5 }] }],
        ['a body that is not JSON', 200, 'not json'],
    ])('keeps the previous panel list after %s', async function(_name, status, body) {
        const { fake, panels } = await composable_load();
        const loaded = panels.panel_metadata_fetch();

        fake.take('/__kaleidoscope__/panels/').resolve(200, { panels: PANELS });
        await loaded;

        const reloaded = panels.panel_metadata_fetch();

        fake.take('/__kaleidoscope__/panels/').resolve(status, body);
        await reloaded;

        expect(panels.panels_available.value).toEqual(PANELS);
    });
});

describe('use_panels hostile answers', function() {
    it('reports a rejection that is not an error as text', async function() {
        vi.stubGlobal('fetch', function() { return Promise.reject('offline'); });
        vi.resetModules();

        const module = await import('../../src/composables/use_panels');
        const panels = module.use_panels(REGISTRY, ref({}));

        panels.panel_active.value = 'timer';
        panels.panel_data_fetch('timer');
        await settled();

        expect(panels.panel_error.value).toBe('offline');
    });

    it.each([
        [null],
        ['panels'],
        [{ panels: 'not a list' }],
        [{ panels: [null] }],
        [{ panels: ['timer'] }],
        [{ panels: [{ id: 'timer', title: 'Timer' }] }],
    ])('keeps its panels when the server answers %j', async function(answer) {
        const { fake, panels } = await composable_load();
        const loading = panels.panel_metadata_fetch();

        fake.take('/panels/').resolve(200, answer);
        await loading;

        expect(panels.panels_available.value).toEqual([]);
        expect(panels.component_active.value).toBeNull();
    });
});

describe('use_panels partial answers', function() {
    it('lists the well-formed panels when one entry is malformed', async function() {
        const { fake, panels } = await composable_load();
        const loading = panels.panel_metadata_fetch();
        const broken = { enabled: true, id: 'custom', isolate: false, summary: '', title: null };

        fake.take('/panels/').resolve(200, { panels: [PANELS[0], broken] });
        await loading;

        const listed = panels.panels_available.value.map(function(panel) { return panel.id; });

        expect(listed).toEqual(['timer']);
    });
});

describe('use_panels contracts', function() {
    it('refuses to fetch the data of a panel that is not active', async function() {
        const { fake, panels } = await composable_load();

        panels.panel_active.value = 'queries';

        expect(function() { panels.panel_data_fetch('timer'); }).toThrow('only the active panel');
        expect(fake.calls).toEqual([]);
    });

    it('finds no component for a panel named like an inherited property', async function() {
        const { panels } = await composable_load();

        panels.panel_active.value = 'constructor';

        expect(panels.component_active.value).toBeNull();
    });

    it('refuses a registry entry that holds no component', async function() {
        vi.resetModules();

        const module = await import('../../src/composables/use_panels');
        const registry = { hollow: undefined } as unknown as Record<string, Component>;
        const panels = module.use_panels(registry, ref({}));

        panels.panel_active.value = 'hollow';

        expect(function() { return panels.component_active.value; }).toThrow('maps no component');
    });
});

