import { ref, computed, shallowRef, type Ref, type ComputedRef, type Component } from 'vue';
import { json_fetch } from '../services/api';
import type { PanelMeta, PanelRegistry } from '../types';

interface UsePanelsReturn {
    panel_active: Ref<string | null>;
    panels_available: Ref<PanelMeta[]>;
    panel_data: Ref<Record<string, unknown> | null>;
    panel_error: Ref<string | null>;
    title_panel: ComputedRef<string>;
    component_active: ComputedRef<Component | null>;
    panel_data_fetch: (panel_id: string) => void;
    panel_metadata_fetch: () => Promise<void>;
}

function component_find(panel_registry: PanelRegistry, panel_id: string | null): Component | null {
    if (panel_id === null) return null;
    if (!Object.hasOwn(panel_registry, panel_id)) return null;

    const component = panel_registry[panel_id];

    if (component === undefined) throw new Error('the registry maps no component to ' + panel_id);

    return component;
}

function error_message(error: unknown): string {
    if (error instanceof Error) return error.message;
    return String(error);
}

function panel_data_fetcher(
    panel_active: Ref<string | null>,
    panel_data: Ref<Record<string, unknown> | null>,
    panel_error: Ref<string | null>,
): (panel_id: string) => void {
    let sequence_data = 0;

    function panel_data_fetch(panel_id: string) {
        if (panel_active.value !== panel_id) {
            throw new Error('only the active panel fetches its data, not ' + panel_id);
        }

        sequence_data += 1;

        const sequence = sequence_data;
        const url = '/__kaleidoscope__/panels/' + panel_id + '/data/';

        json_fetch<Record<string, unknown>>(url).then(function(data) {
            if (sequence !== sequence_data) return;
            if (panel_active.value !== panel_id) return;

            panel_data.value = data;
            panel_error.value = null;
        }).catch(function(error: unknown) {
            if (sequence !== sequence_data) return;
            if (panel_active.value !== panel_id) return;

            panel_error.value = error_message(error);
        });
    }

    return panel_data_fetch;
}

function panel_title_find(panels: PanelMeta[], panel_id: string | null): string {
    const panel = panels.find(function(candidate) {
        return candidate.id === panel_id;
    });

    return panel ? panel.title : '';
}

function panel_valid(value: unknown): value is PanelMeta {
    if (value === null) return false;
    if (typeof value !== 'object') return false;

    const panel = value as Record<string, unknown>;

    return typeof panel['id'] === 'string'
        && typeof panel['title'] === 'string'
        && typeof panel['summary'] === 'string'
        && typeof panel['enabled'] === 'boolean'
        && typeof panel['isolate'] === 'boolean';
}

function panels_disabled_mirror(panels: PanelMeta[]): Record<string, boolean> {
    const mirrored: Record<string, boolean> = {};

    for (const panel of panels) {
        mirrored[panel.id] = !panel.enabled;
    }

    return mirrored;
}

function panels_read(value: unknown): PanelMeta[] | null {
    if (value === null) return null;
    if (typeof value !== 'object') return null;

    const panels = (value as { panels?: unknown }).panels;

    if (!Array.isArray(panels)) return null;

    const valid = panels.filter(panel_valid);

    if (panels.length > 0) {
        if (valid.length === 0) return null;
    }

    return valid;
}

export function use_panels(
    panel_registry: PanelRegistry,
    panels_disabled: Ref<Record<string, boolean>>,
): UsePanelsReturn {
    const panel_active = ref<string | null>(null);
    const panels_available = ref<PanelMeta[]>([]);
    const panel_data = shallowRef<Record<string, unknown> | null>(null);
    const panel_error = ref<string | null>(null);
    const panel_data_fetch = panel_data_fetcher(panel_active, panel_data, panel_error);

    let sequence_metadata = 0;

    const title_panel = computed(function() {
        return panel_title_find(panels_available.value, panel_active.value);
    });

    const component_active = computed(function(): Component | null {
        return component_find(panel_registry, panel_active.value);
    });

    function panel_metadata_fetch(): Promise<void> {
        sequence_metadata += 1;

        const sequence = sequence_metadata;

        return json_fetch('/__kaleidoscope__/panels/').then(function(data) {
            const panels = panels_read(data);

            if (sequence !== sequence_metadata) return;
            if (panels === null) return;

            panels_available.value = panels;
            panels_disabled.value = { ...panels_disabled.value, ...panels_disabled_mirror(panels) };
        }).catch(function() {
            return undefined;
        });
    }

    return {
        panel_active,
        panels_available,
        panel_data,
        panel_error,
        title_panel,
        component_active,
        panel_data_fetch,
        panel_metadata_fetch,
    };
}
