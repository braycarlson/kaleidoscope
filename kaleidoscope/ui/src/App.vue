<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { ArrowLeft, X } from 'lucide-vue-next';
import KaleidoscopeTab from './components/KaleidoscopeTab.vue';
import KaleidoscopeStrip from './components/KaleidoscopeStrip.vue';
import CopyButton from './components/CopyButton.vue';
import CachePanel from './components/panels/CachePanel.vue';
import LineProfilingPanel from './components/panels/LineProfilerPanel.vue';
import MemoryPanel from './components/panels/MemoryPanel.vue';
import ProfilingPanel from './components/panels/ProfilingPanel.vue';
import QueriesPanel from './components/panels/QueriesPanel.vue';
import RequestPanel from './components/panels/RequestPanel.vue';
import SettingsPanel from './components/panels/SettingsPanel.vue';
import SignalsPanel from './components/panels/SignalsPanel.vue';
import StaticFilesPanel from './components/panels/StaticFilesPanel.vue';
import TemplatesPanel from './components/panels/TemplatesPanel.vue';
import TimerPanel from './components/panels/TimerPanel.vue';
import VersionsPanel from './components/panels/VersionsPanel.vue';
import { use_interceptors } from './composables/use_interceptors';
import { use_mobile } from './composables/use_mobile';
import { use_panels } from './composables/use_panels';
import { use_preferences } from './composables/use_preferences';
import { json_fetch } from './services/api';
import { DEBOUNCE_MS } from './constants';
import type { KaleidoscopeState, PanelRegistry } from './types';

const panel_registry: PanelRegistry = {
    'cache': CachePanel,
    'line_profiling': LineProfilingPanel,
    'memory': MemoryPanel,
    'profiling': ProfilingPanel,
    'queries': QueriesPanel,
    'request': RequestPanel,
    'settings': SettingsPanel,
    'signals': SignalsPanel,
    'staticfiles': StaticFilesPanel,
    'templates': TemplatesPanel,
    'timer': TimerPanel,
    'versions': VersionsPanel,
};

const state = ref<KaleidoscopeState>('collapsed');
let timer_fetch: ReturnType<typeof setTimeout> | null = null;
let interceptors_cleanup: (() => void) | null = null;

const { is_mobile } = use_mobile();
const { panel_order, panels_disabled, side, preferences_save, preferences_load } = use_preferences();
const {
    panel_active,
    panels_available,
    panel_data,
    title_panel,
    component_active,
    panel_data_fetch,
    panel_metadata_fetch,
} = use_panels(panel_registry, panels_disabled);

function save() {
    preferences_save(state.value, panel_active.value);
}

function strip_return() {
    panel_active.value = null;
    panel_data.value = null;
    state.value = 'strip';
    save();
}

function overlay_close() {
    state.value = 'strip';
    panel_active.value = null;
    panel_data.value = null;
    save();
}

function strip_close() {
    state.value = 'collapsed';
    panel_active.value = null;
    panel_data.value = null;
    save();
}

function strip_open() {
    state.value = 'strip';
    save();
}

function panel_open(panel_id: string) {
    state.value = 'panel';
    panel_active.value = panel_id;
    panel_data.value = null;
    panel_data_fetch(panel_id);
    save();
}

function panel_select(panel_id: string) {
    if (panel_active.value === panel_id) {
        overlay_close();
    } else {
        panel_open(panel_id);
    }
}

function panels_reorder(order_new: string[]) {
    panel_order.value = order_new;
    save();
}

function panel_refresh() {
    if (panel_active.value) {
        panel_data_fetch(panel_active.value);
    }

    panel_metadata_fetch();
}

function panel_enabled_toggle(panel_id: string) {
    const currently_disabled = panels_disabled.value[panel_id];
    const action = currently_disabled ? 'enable' : 'disable';

    json_fetch('/__kaleidoscope__/panels/' + panel_id + '/' + action + '/').then(function() {
        panels_disabled.value = { ...panels_disabled.value, [panel_id]: !currently_disabled };

        if (!currently_disabled && panel_active.value === panel_id) {
            overlay_close();
        }

        save();
        panel_metadata_fetch();
    });
}

function side_swap() {
    side.value = side.value === 'right' ? 'left' : 'right';
    save();
}

function refresh_debounced() {
    if (timer_fetch) clearTimeout(timer_fetch);

    timer_fetch = setTimeout(function() {
        timer_fetch = null;
        panel_metadata_fetch();

        if (panel_active.value) {
            panel_data_fetch(panel_active.value);
        }
    }, DEBOUNCE_MS);
}

onMounted(function() {
    preferences_load(panel_registry, function(restored_state, panel_id) {
        state.value = restored_state;

        if (panel_id) {
            panel_active.value = panel_id;
            panel_data_fetch(panel_id);
        }
    });

    panel_metadata_fetch();
    interceptors_cleanup = use_interceptors(refresh_debounced);
});

onUnmounted(function() {
    if (timer_fetch) {
        clearTimeout(timer_fetch);
        timer_fetch = null;
    }

    if (interceptors_cleanup) {
        interceptors_cleanup();
        interceptors_cleanup = null;
    }
});
</script>

<template>
    <div class="font-sans text-[13px] text-[#d0d0e0] leading-normal">
        <KaleidoscopeTab
            v-if="state === 'collapsed'"
            :side="side"
            @open="strip_open"
        />

        <div
            v-if="state !== 'collapsed'"
            class="fixed inset-0 z-[999999] flex"
            :class="{
                'left-auto sm:left-auto': state === 'strip' && !is_mobile && side === 'right',
                'right-auto sm:right-auto': state === 'strip' && !is_mobile && side === 'left',
                'flex-row-reverse': side === 'left',
            }"
            @mousedown.stop
            @click.stop
        >
            <div
                v-if="panel_active && !(is_mobile && state === 'strip')"
                class="flex flex-col flex-1 min-w-0 bg-[#12121e] border-white/10"
                :class="side === 'right' ? 'border-l' : 'border-r'"
            >
                <div class="flex items-center justify-between px-3 sm:px-5 py-3 border-b border-white/[0.08] bg-[#0e0e1a] shrink-0">
                    <div class="flex items-center gap-3 min-w-0">
                        <button
                            v-if="is_mobile"
                            class="shrink-0 text-gray-500 hover:text-white"
                            @click="strip_return"
                        >
                            <ArrowLeft :size="18" />
                        </button>
                        <span class="font-semibold text-sm truncate">{{ title_panel }}</span>
                        <CopyButton
                            v-if="panel_data"
                            :value="panel_data"
                        />
                    </div>
                    <button class="shrink-0 text-gray-500 hover:text-white ml-3" @click="overlay_close">
                        <X :size="18" />
                    </button>
                </div>
                <div class="flex-1 overflow-y-auto p-3 sm:p-5 flex flex-col">
                    <component
                        :is="component_active"
                        v-if="panel_data && component_active"
                        :data="panel_data"
                        @refresh="panel_refresh"
                    />
                    <div v-else class="py-10 text-center opacity-30 italic">Loading...</div>
                </div>
            </div>

            <KaleidoscopeStrip
                v-if="!is_mobile || state === 'strip'"
                :panels="panels_available"
                :panel_active="panel_active"
                :panel_order="panel_order"
                :panels_disabled="panels_disabled"
                :side="side"
                :is_mobile="is_mobile"
                @select="panel_select"
                @close="strip_close"
                @swap="side_swap"
                @toggle="panel_enabled_toggle"
                @reorder="panels_reorder"
            />
        </div>
    </div>
</template>
