import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import { fetch_fake_create, settled, type FetchFake } from '../support/fetch';

const PANELS = Object.freeze([
    { enabled: true, id: 'timer', isolate: false, summary: '', title: 'Timer' },
    { enabled: true, id: 'queries', isolate: false, summary: '', title: 'SQL Queries' },
]);

const REQUEST = Object.freeze({
    duration: 3,
    is_ajax: false,
    method: 'GET',
    path: '/books/',
    queries: [],
    query_count: 0,
    query_time: 0,
    status_code: 200,
    timestamp: 1,
});

const QUERIES = Object.freeze({
    duplicates: {},
    requests: [REQUEST],
    similar: {},
    summary: { request_count: 1, total_queries: 0, total_query_time: 0 },
    track_ajax: true,
    track_page: true,
});

function width_set(width: number) {
    const descriptor = { configurable: true, value: width, writable: true };

    Object.defineProperty(window, 'innerWidth', descriptor);
}

const PANELS_ISOLATED = Object.freeze([
    { enabled: true, id: 'timer', isolate: false, summary: '', title: 'Timer' },
    { enabled: true, id: 'memory', isolate: true, summary: '', title: 'Memory' },
    { enabled: false, id: 'profiling', isolate: true, summary: '', title: 'Profiling' },
]);

const PANELS_ISOLATED_SWAPPED = Object.freeze([
    { enabled: true, id: 'timer', isolate: false, summary: '', title: 'Timer' },
    { enabled: false, id: 'memory', isolate: true, summary: '', title: 'Memory' },
    { enabled: true, id: 'profiling', isolate: true, summary: '', title: 'Profiling' },
]);

interface AppTransitions {
    overlay_close: () => void;
    strip_close: () => void;
    strip_open: () => void;
    strip_return: () => void;
}

async function app_mount(
    width: number,
    panels: readonly object[] = PANELS,
): Promise<{ fake: FetchFake; wrapper: VueWrapper }> {
    const fake = fetch_fake_create();

    localStorage.clear();
    width_set(width);
    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../src/App.vue');
    const wrapper = mount(module.default as Component, { attachTo: document.body }) as VueWrapper;

    await flushPromises();

    fake.take('/__kaleidoscope__/panels/').resolve(200, { panels: panels });
    await settled();

    const tab = wrapper.get('[data-ks="tab"]');

    await tab.trigger('mousedown', { clientY: 300 });
    document.dispatchEvent(new MouseEvent('mouseup', { clientY: 300 }));
    await flushPromises();

    return { fake, wrapper };
}

afterEach(function() {
    width_set(1024);
    document.body.innerHTML = '';
});

describe('App', function() {
    it('returns from a panel to the strip on a narrow screen', async function() {
        const { fake, wrapper } = await app_mount(420);

        await wrapper.get('[data-ks-panel="timer"]').trigger('click');
        fake.take('/panels/timer/data/').resolve(200, { total_ms: 5 });
        await settled();

        expect(wrapper.find('[data-ks="strip"]').exists()).toBe(false);

        await wrapper.get('[data-ks="panel-back"]').trigger('click');

        expect(wrapper.find('[data-ks="strip"]').exists()).toBe(true);
        expect(wrapper.find('[data-ks="panel"]').exists()).toBe(false);

        wrapper.unmount();
    });

    it('reloads the panel and the panel list when the panel asks for a refresh', async function() {
        const { fake, wrapper } = await app_mount(1280);

        await wrapper.get('[data-ks-panel="queries"]').trigger('click');
        fake.take('/panels/queries/data/').resolve(200, QUERIES);
        await settled();
        await wrapper.get('button[aria-label="Clear the recorded requests"]').trigger('click');
        fake.take('/queries/action/clear/').resolve(200, { success: true });
        await settled();

        expect(fake.pending.map(function(request) { return request.url; })).toEqual([
            '/__kaleidoscope__/panels/queries/data/',
            '/__kaleidoscope__/panels/',
        ]);

        wrapper.unmount();
    });

    it('saves the isolated panel the server kept after a toggle', async function() {
        const { fake, wrapper } = await app_mount(1280, PANELS_ISOLATED);

        await wrapper.get('[data-ks-toggle="profiling"]').trigger('click');
        fake.take('/panels/profiling/enable/').resolve(200, { enabled: true });
        await settled();
        fake.take('/__kaleidoscope__/panels/').resolve(200, { panels: PANELS_ISOLATED_SWAPPED });
        await settled();

        const raw = localStorage.getItem('kaleidoscope_preferences') ?? '{}';
        const saved = JSON.parse(raw) as { disabled: Record<string, boolean> };

        expect(saved.disabled).toEqual({ memory: true, profiling: false, timer: false });
        expect(wrapper.get('[data-ks-toggle="memory"]').attributes('aria-checked')).toBe('false');

        wrapper.unmount();
    });

    it('refuses a transition that none of its controls can ask for', async function() {
        const { wrapper } = await app_mount(1280);
        const app = wrapper.vm as unknown as AppTransitions;

        expect(app.strip_open).toThrow('the strip opens only from the collapsed tab, not strip');
        expect(app.overlay_close).toThrow('only an open panel can be closed');
        expect(app.strip_return).toThrow('only an open panel returns to the strip');

        app.strip_close();

        expect(app.strip_close).toThrow('a collapsed toolbar has no strip to close');

        wrapper.unmount();
    });
});
