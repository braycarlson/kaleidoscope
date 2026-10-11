import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent } from 'vue';
import { fetch_fake_create, settled } from '../support/fetch';

const DUMMY = defineComponent({ template: '<div />' });
const LAUNCH = 'launch-1';
const RECORDS_INVALID = Object.freeze(['', 'not json', 'null', '7', '"text"', '[]']);
const REGISTRY = Object.freeze({ cache: DUMMY, queries: DUMMY, timer: DUMMY });
const STORAGE_KEY = 'kaleidoscope_preferences';

async function module_load() {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    const module = await import('../../src/composables/use_preferences');

    return { ...module, fake };
}

function stored(value: unknown) {
    localStorage.setItem(STORAGE_KEY, typeof value === 'string' ? value : JSON.stringify(value));
}

function storage_refuse(): never {
    throw new Error('storage is denied');
}

beforeEach(function() {
    localStorage.clear();
});

describe('preferences_parse', function() {
    it('reads a well-formed preference record', async function() {
        const { preferences_parse } = await module_load();

        const parsed = preferences_parse(JSON.stringify({
            active_panel: 'queries',
            disabled: { cache: true },
            launch: LAUNCH,
            order: ['timer', 'queries'],
            side: 'left',
            state: 'panel',
        }));

        expect(parsed).toEqual({
            active_panel: 'queries',
            disabled: { cache: true },
            launch: LAUNCH,
            order: ['timer', 'queries'],
            side: 'left',
            state: 'panel',
        });
    });

    it.each(RECORDS_INVALID)('refuses a record that is not an object: %s', async function(raw) {
        const { preferences_parse } = await module_load();

        expect(preferences_parse(raw)).toBeNull();
    });

    it('replaces every malformed field with its default', async function() {
        const { preferences_parse } = await module_load();

        const parsed = preferences_parse(JSON.stringify({
            active_panel: 5,
            disabled: { cache: 'yes', queries: false, timer: null },
            launch: 7,
            order: ['timer', 3, 'timer', null, 'cache'],
            side: 'up',
            state: 'floating',
        }));

        expect(parsed).toEqual({
            active_panel: null,
            disabled: { queries: false },
            launch: '',
            order: ['timer', 'cache'],
            side: 'right',
            state: 'collapsed',
        });
    });

    it('bounds the order and disabled collections', async function() {
        const { preferences_parse } = await module_load();

        const identifiers = Array.from({ length: 500 }, function(_, index) {
            return 'panel' + index;
        });

        const disabled = Object.fromEntries(identifiers.map(function(id) { return [id, true]; }));
        const record = JSON.stringify({ disabled: disabled, order: identifiers });
        const parsed = preferences_parse(record);

        expect(parsed?.order.length).toBe(64);
        expect(Object.keys(parsed?.disabled ?? {}).length).toBe(64);
    });
});

describe('use_preferences save', function() {
    it('saves the toolbar state and reads it back', async function() {
        const { use_preferences } = await module_load();
        const preferences = use_preferences(LAUNCH);

        preferences.panel_order.value = ['queries'];
        preferences.panels_disabled.value = { cache: true };
        preferences.side.value = 'left';
        preferences.preferences_save('panel', 'queries');

        expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '')).toEqual({
            active_panel: 'queries',
            disabled: { cache: true },
            launch: LAUNCH,
            order: ['queries'],
            side: 'left',
            state: 'panel',
        });
    });

    it('survives storage that refuses every read and write', async function() {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(storage_refuse);
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(storage_refuse);

        const { use_preferences } = await module_load();
        const preferences = use_preferences(LAUNCH);

        await preferences.preferences_load(REGISTRY, vi.fn());
        preferences.preferences_save('strip', null);

        expect(preferences.side.value).toBe('right');
    });
});

describe('use_preferences restore', function() {
    it('restores the state and the open panel and replays each known toggle', async function() {
        stored({
            active_panel: 'queries',
            disabled: { cache: true, timer: false, retired: true },
            launch: LAUNCH,
            order: ['queries'],
            side: 'left',
            state: 'panel',
        });

        const { fake, use_preferences } = await module_load();
        const preferences = use_preferences(LAUNCH);
        const restored = vi.fn();
        const loaded = preferences.preferences_load(REGISTRY, restored);

        expect(restored).toHaveBeenCalledWith('panel', 'queries');
        expect(preferences.side.value).toBe('left');
        expect(preferences.panel_order.value).toEqual(['queries']);

        expect(fake.calls).toEqual([
            '/__kaleidoscope__/panels/cache/disable/',
            '/__kaleidoscope__/panels/timer/enable/',
        ]);

        let finished = false;

        void loaded.then(function() { finished = true; });
        await settled();

        expect(finished).toBe(false);

        fake.resolve_all(function() { return [200, { enabled: true }]; });
        await loaded;
    });

    it('opens the strip instead of a panel the registry does not have', async function() {
        stored({ active_panel: 'constructor', launch: LAUNCH, state: 'panel' });

        const { use_preferences } = await module_load();
        const restored = vi.fn();

        await use_preferences(LAUNCH).preferences_load(REGISTRY, restored);

        expect(restored).toHaveBeenCalledWith('strip', null);
    });
});

describe('use_preferences restore collapsed', function() {
    it('starts collapsed when an earlier server launch saved the open panel', async function() {
        stored({
            active_panel: 'queries',
            disabled: { cache: true },
            launch: 'launch-0',
            side: 'left',
            state: 'panel',
        });

        const { fake, use_preferences } = await module_load();
        const preferences = use_preferences(LAUNCH);
        const restored = vi.fn();
        const loaded = preferences.preferences_load(REGISTRY, restored);

        expect(restored).not.toHaveBeenCalled();
        expect(preferences.side.value).toBe('left');
        expect(fake.calls).toEqual(['/__kaleidoscope__/panels/cache/disable/']);

        fake.resolve_all(function() { return [200, { enabled: false }]; });
        await loaded;
    });

    it('stays collapsed and keeps defaults when nothing is stored', async function() {
        const { use_preferences } = await module_load();
        const preferences = use_preferences(LAUNCH);
        const restored = vi.fn();

        await preferences.preferences_load(REGISTRY, restored);

        expect(restored).not.toHaveBeenCalled();
        expect(preferences.side.value).toBe('right');
        expect(preferences.panel_order.value).toEqual([]);
    });
});

describe('use_preferences replay', function() {
    it('never replays a toggle for an inherited property name', async function() {
        const disabled = { constructor: true, toString: false, __proto__: true };

        stored({ disabled, state: 'strip' });

        const { fake, use_preferences } = await module_load();

        await use_preferences(LAUNCH).preferences_load(REGISTRY, vi.fn());

        expect(fake.calls).toEqual([]);
    });

    it('finishes loading even when a replayed toggle fails', async function() {
        stored({ disabled: { cache: true }, state: 'strip' });

        const { fake, use_preferences } = await module_load();
        const loaded = use_preferences(LAUNCH).preferences_load(REGISTRY, vi.fn());

        fake.take('/panels/cache/disable/').fail('Failed to fetch');

        await expect(loaded).resolves.toBeUndefined();
    });
});

describe('use_preferences save contract', function() {
    it('refuses an open state without its panel and a panel left closed', async function() {
        const { use_preferences } = await module_load();
        const preferences = use_preferences(LAUNCH);

        function save_open_unnamed() {
            preferences.preferences_save('panel', null);
        }

        function save_named_closed() {
            preferences.preferences_save('strip', 'queries');
        }

        expect(save_open_unnamed).toThrow('an open panel state must name its panel');
        expect(save_named_closed).toThrow('a named panel must be saved open: strip');
        expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    });
});

