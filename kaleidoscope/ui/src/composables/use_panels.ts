import { ref, computed, type Ref, type ComputedRef, type Component } from 'vue';
import { json_fetch } from '../services/api';
import type { PanelMeta, PanelRegistry } from '../types';

interface UsePanelsReturn {
    panel_active: Ref<string | null>;
    panels_available: Ref<PanelMeta[]>;
    panel_data: Ref<Record<string, unknown> | null>;
    title_panel: ComputedRef<string>;
    component_active: ComputedRef<Component | null>;
    panel_data_fetch: (panel_id: string) => void;
    panel_metadata_fetch: () => void;
}

export function use_panels(
    panel_registry: PanelRegistry,
    panels_disabled: Ref<Record<string, boolean>>,
): UsePanelsReturn {
    const panel_active = ref<string | null>(null);
    const panels_available = ref<PanelMeta[]>([]);
    const panel_data = ref<Record<string, unknown> | null>(null);

    const title_panel = computed(function() {
        const panel = panels_available.value.find(function(p) {
            return p.id === panel_active.value;
        });

        return panel ? panel.title : '';
    });

    const component_active = computed(function(): Component | null {
        return panel_active.value ? panel_registry[panel_active.value] || null : null;
    });

    function panel_data_fetch(panel_id: string) {
        json_fetch<Record<string, unknown>>('/__kaleidoscope__/panels/' + panel_id + '/data/').then(function(data) {
            if (panel_active.value === panel_id) {
                panel_data.value = data;
            }
        });
    }

    function panel_metadata_fetch() {
        json_fetch<{ panels: PanelMeta[] }>('/__kaleidoscope__/panels/').then(function(data) {
            panels_available.value = data.panels;

            const server_disabled: Record<string, boolean> = {};

            data.panels.forEach(function(panel) {
                if (!panel.enabled) {
                    server_disabled[panel.id] = true;
                }
            });

            panels_disabled.value = { ...panels_disabled.value, ...server_disabled };
        });
    }

    return {
        panel_active,
        panels_available,
        panel_data,
        title_panel,
        component_active,
        panel_data_fetch,
        panel_metadata_fetch,
    };
}
