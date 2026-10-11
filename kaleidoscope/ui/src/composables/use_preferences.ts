import { ref, type Ref } from 'vue';
import { json_fetch } from '../services/api';
import { storage_read, storage_write } from '../services/storage';
import type { KaleidoscopeSide, KaleidoscopeState, PanelRegistry } from '../types';

interface Preferences {
    active_panel: string | null;
    disabled: Record<string, boolean>;
    launch: string;
    order: string[];
    side: KaleidoscopeSide;
    state: KaleidoscopeState;
}

interface UsePreferencesReturn {
    panel_order: Ref<string[]>;
    panels_disabled: Ref<Record<string, boolean>>;
    side: Ref<KaleidoscopeSide>;
    preferences_save: (state: KaleidoscopeState, panel_active: string | null) => void;
    preferences_load: (
        panel_registry: PanelRegistry,
        on_restore: (state: KaleidoscopeState, panel_id: string | null) => void,
    ) => Promise<void>;
}

const PANELS_MAX = 64;
const SIDES: readonly string[] = Object.freeze(['left', 'right']);
const STATES: readonly string[] = Object.freeze(['collapsed', 'strip', 'panel']);
const STORAGE_KEY = 'kaleidoscope_preferences';

function choice_read(value: unknown, choices: readonly string[], fallback: string): string {
    if (typeof value !== 'string') return fallback;
    if (!choices.includes(value)) return fallback;
    return value;
}

function record_is(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function disabled_read(value: unknown): Record<string, boolean> {
    const disabled: Record<string, boolean> = {};

    if (!record_is(value)) return disabled;

    for (const id of Object.keys(value).slice(0, PANELS_MAX)) {
        const entry = value[id];

        if (typeof entry === 'boolean') {
            disabled[id] = entry;
        }
    }

    return disabled;
}

function order_read(value: unknown): string[] {
    const order: string[] = [];

    if (!Array.isArray(value)) return order;

    for (const id of value) {
        if (order.length >= PANELS_MAX) break;
        if (typeof id !== 'string') continue;
        if (order.includes(id)) continue;

        order.push(id);
    }

    return order;
}

function preferences_save_validate(state: KaleidoscopeState, panel_active: string | null) {
    if (state === 'panel') {
        if (panel_active === null) throw new Error('an open panel state must name its panel');
    }

    if (panel_active !== null) {
        if (state !== 'panel') throw new Error('a named panel must be saved open: ' + state);
    }
}

export function preferences_parse(raw: string): Preferences | null {
    let parsed: unknown;

    try {
        parsed = JSON.parse(raw);
    } catch {
        return null;
    }

    if (!record_is(parsed)) return null;

    const active_panel = parsed['active_panel'];
    const launch = parsed['launch'];
    const side = choice_read(parsed['side'], SIDES, 'right');
    const state = choice_read(parsed['state'], STATES, 'collapsed');

    return {
        active_panel: typeof active_panel === 'string' ? active_panel : null,
        disabled: disabled_read(parsed['disabled']),
        launch: typeof launch === 'string' ? launch : '',
        order: order_read(parsed['order']),
        side: side as KaleidoscopeSide,
        state: state as KaleidoscopeState,
    };
}

export function use_preferences(launch: string): UsePreferencesReturn {
    const panel_order = ref<string[]>([]);
    const panels_disabled = ref<Record<string, boolean>>({});
    const side = ref<KaleidoscopeSide>('right');

    function preferences_save(state: KaleidoscopeState, panel_active: string | null) {
        preferences_save_validate(state, panel_active);

        const preferences: Preferences = {
            active_panel: panel_active,
            disabled: panels_disabled.value,
            launch: launch,
            order: panel_order.value,
            side: side.value,
            state: state,
        };

        void storage_write(STORAGE_KEY, JSON.stringify(preferences));
    }

    function preferences_load(
        panel_registry: PanelRegistry,
        on_restore: (state: KaleidoscopeState, panel_id: string | null) => void,
    ): Promise<void> {
        const raw = storage_read(STORAGE_KEY);
        const preferences = raw === null ? null : preferences_parse(raw);

        if (preferences === null) return Promise.resolve();

        panel_order.value = preferences.order;
        panels_disabled.value = preferences.disabled;
        side.value = preferences.side;
        const state = preferences.launch === launch ? preferences.state : 'collapsed';

        if (state !== 'collapsed') {
            const panel_id = preferences.active_panel;
            const panel_known = panel_id !== null && Object.hasOwn(panel_registry, panel_id);
            const panel_restored = state === 'panel' && panel_known;

            if (panel_restored) {
                on_restore('panel', panel_id);
            } else {
                on_restore('strip', null);
            }
        }

        const replays: Promise<unknown>[] = [];

        for (const id of Object.keys(preferences.disabled)) {
            if (!Object.hasOwn(panel_registry, id)) continue;

            const action = preferences.disabled[id] ? 'disable' : 'enable';
            const url = '/__kaleidoscope__/panels/' + id + '/' + action + '/';

            const replay = json_fetch(url).catch(function() {
                return undefined;
            });

            replays.push(replay);
        }

        return Promise.all(replays).then(function() {
            return undefined;
        });
    }

    return { panel_order, panels_disabled, side, preferences_save, preferences_load };
}
