import { ref, type Ref } from 'vue';
import type { KaleidoscopeSide, KaleidoscopeState, PanelRegistry } from '../types';

interface Preferences {
    active_panel: string | null;
    disabled: Record<string, boolean>;
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
    ) => void;
}

export function use_preferences(): UsePreferencesReturn {
    const panel_order = ref<string[]>([]);
    const panels_disabled = ref<Record<string, boolean>>({});
    const side = ref<KaleidoscopeSide>('right');

    function preferences_save(state: KaleidoscopeState, panel_active: string | null) {
        try {
            localStorage.setItem('kaleidoscope_preferences', JSON.stringify({
                active_panel: panel_active,
                disabled: panels_disabled.value,
                order: panel_order.value,
                side: side.value,
                state: state,
            }));
        } catch {
            // localStorage may be unavailable
        }
    }

    function preferences_load(
        panel_registry: PanelRegistry,
        on_restore: (state: KaleidoscopeState, panel_id: string | null) => void,
    ) {
        try {
            const raw = localStorage.getItem('kaleidoscope_preferences');

            if (raw) {
                const preferences: Preferences = JSON.parse(raw);
                panel_order.value = preferences.order || [];
                panels_disabled.value = preferences.disabled || {};
                side.value = preferences.side || 'right';

                if (preferences.state && preferences.state !== 'collapsed') {
                    let panel_id: string | null = null;

                    if (
                        preferences.active_panel
                        && preferences.state === 'panel'
                        && preferences.active_panel in panel_registry
                    ) {
                        panel_id = preferences.active_panel;
                    }

                    on_restore(preferences.state, panel_id);
                }

                for (const id in preferences.disabled) {
                    if (!(id in panel_registry)) {
                        continue;
                    }

                    if (preferences.disabled[id]) {
                        import('../services/api').then(function(api) {
                            api.json_fetch('/__kaleidoscope__/panels/' + id + '/disable/');
                        });
                    } else {
                        import('../services/api').then(function(api) {
                            api.json_fetch('/__kaleidoscope__/panels/' + id + '/enable/');
                        });
                    }
                }
            }
        } catch {
            panel_order.value = [];
            panels_disabled.value = {};
            side.value = 'right';
        }
    }

    return { panel_order, panels_disabled, side, preferences_save, preferences_load };
}
