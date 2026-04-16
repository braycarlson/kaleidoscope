<script setup lang="ts">
import { ref, computed } from 'vue';
import { Info, X, GripVertical, PanelLeft, PanelLeftClose, PanelRight, PanelRightClose } from 'lucide-vue-next';
import type { KaleidoscopeSide, PanelMeta } from '../types';

const props = withDefaults(defineProps<{
    panels: PanelMeta[];
    panel_active?: string | null;
    panel_order?: string[];
    panels_disabled?: Record<string, boolean>;
    side?: KaleidoscopeSide;
    is_mobile?: boolean;
}>(), {
    panel_active: null,
    panel_order: () => [],
    panels_disabled: () => ({}),
    side: 'right',
    is_mobile: false,
});

const emit = defineEmits<{
    select: [panel_id: string];
    close: [];
    swap: [];
    toggle: [panel_id: string];
    reorder: [order: string[]];
}>();

const index_drag = ref<number | null>(null);
const index_drag_over = ref<number | null>(null);

const panels_ordered = computed(function() {
    if (!props.panel_order.length) return props.panels;

    const order_map: Record<string, number> = {};

    props.panel_order.forEach(function(id, index) {
        order_map[id] = index;
    });

    return props.panels.slice().sort(function(a, b) {
        const index_a = order_map[a.id] !== undefined ? order_map[a.id] : 999;
        const index_b = order_map[b.id] !== undefined ? order_map[b.id] : 999;
        return index_a - index_b;
    });
});

const is_isolated = computed(function() {
    return panels_ordered.value.some(function(panel) {
        return panel.isolate && is_enabled(panel.id);
    });
});

function is_enabled(panel_id: string): boolean {
    return !props.panels_disabled[panel_id];
}

function is_paused(panel: PanelMeta): boolean {
    return is_isolated.value && !panel.isolate && is_enabled(panel.id);
}

function on_click(panel: PanelMeta) {
    if (is_enabled(panel.id)) {
        emit('select', panel.id);
    }
}

function on_drag_start(index: number, event: DragEvent) {
    index_drag.value = index;
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
    }
}

function on_drag_over(index: number, event: DragEvent) {
    event.preventDefault();
    index_drag_over.value = index;
}

function on_drop(index: number) {
    if (index_drag.value === null || index_drag.value === index) return;

    const ids = panels_ordered.value.map(function(panel) { return panel.id; });
    const moved = ids.splice(index_drag.value, 1)[0];
    ids.splice(index, 0, moved);
    emit('reorder', ids);
    index_drag.value = null;
    index_drag_over.value = null;
}

function on_drag_end() {
    index_drag.value = null;
    index_drag_over.value = null;
}
</script>

<template>
    <div
        class="flex flex-col bg-black/95 backdrop-blur-md shrink-0"
        :class="[
            is_mobile ? 'w-full' : 'w-64 min-w-[256px]',
            side === 'right' ? 'border-l border-white/10' : 'border-r border-white/10',
        ]"
    >
        <div
            class="flex items-center justify-between px-3.5 py-3 shrink-0 cursor-pointer transition-colors hover:bg-white/[0.03] group"
            style="border-bottom: 1px solid rgba(255, 255, 255, 0.15)"
            @click="emit('close')"
        >
            <span class="font-semibold text-sm text-gray-400 group-hover:text-gray-300 transition-colors">Kaleidoscope</span>
            <X :size="16" class="text-gray-400 group-hover:text-white transition-colors" />
        </div>

        <div v-if="is_isolated" class="mx-3 mt-3 relative">
            <div class="px-3 py-2.5 bg-orange-500/10 border border-orange-500/20 rounded text-[11px] text-center leading-relaxed flex items-center justify-center gap-1.5">
                <span class="font-semibold text-orange-400">Isolation Mode</span>
                <div class="group inline-flex items-center">
                    <Info :size="13" class="text-orange-400/50 group-hover:text-orange-400 cursor-help" />
                    <div class="absolute top-full left-0 right-0 mt-1 px-3 py-2.5 bg-[#0e0e1a] border border-white/[0.15] rounded text-[11px] text-gray-300 leading-relaxed hidden group-hover:block pointer-events-none z-10">
                        There is at least one enabled panel that is running in isolation mode. These panel(s) are isolated to measure performance and run exclusively to keep the measurement more accurate. As such, other panels will not record new information.
                    </div>
                </div>
            </div>
        </div>

        <div class="flex-1 overflow-y-auto py-2">
            <div
                v-for="(panel, index) in panels_ordered"
                :key="panel.id"
                draggable="true"
                class="flex items-center gap-1 pr-3 transition-colors"
                :class="[
                    panel_active === panel.id
                        ? (side === 'right' ? 'border-l-[3px] border-purple-700' : 'border-r-[3px] border-purple-700') + ' bg-white/[0.06]'
                        : (side === 'right' ? 'border-l-[3px]' : 'border-r-[3px]') + ' border-transparent hover:bg-white/[0.03]',
                    index_drag_over === index && index_drag !== index
                        ? 'border-t border-t-purple-500'
                        : '',
                    index_drag === index ? 'opacity-40' : '',
                    !is_enabled(panel.id) ? 'opacity-30' : '',
                    is_paused(panel) ? 'opacity-45' : '',
                ]"
                @dragstart="on_drag_start(index, $event)"
                @dragover="on_drag_over(index, $event)"
                @drop="on_drop(index)"
                @dragend="on_drag_end"
            >
                <div class="px-1 cursor-grab opacity-20 hover:opacity-40 shrink-0 hidden sm:block">
                    <GripVertical :size="12" />
                </div>

                <button
                    class="flex flex-col gap-0.5 flex-1 py-2.5 text-left text-sm"
                    :class="[
                        is_mobile ? 'pl-3 sm:pl-0' : '',
                        is_enabled(panel.id)
                            ? (panel_active === panel.id ? 'text-white' : 'text-gray-300 hover:text-white')
                            : 'text-gray-600 cursor-default',
                    ]"
                    @click="on_click(panel)"
                >
                    <span class="font-semibold">{{ panel.title }}</span>
                    <span class="text-[11px] opacity-50">
                        <template v-if="is_paused(panel)">
                            <span class="text-orange-400/60 italic">paused</span>
                        </template>
                        <template v-else>
                            {{ panel.summary }}
                        </template>
                    </span>
                </button>

                <div
                    class="relative w-7 h-4 rounded-full transition-colors cursor-pointer shrink-0"
                    :class="is_enabled(panel.id) ? 'bg-purple-600' : 'bg-white/10'"
                    @click.stop="emit('toggle', panel.id)"
                >
                    <div
                        class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform"
                        :class="{ 'translate-x-3': is_enabled(panel.id) }"
                    />
                </div>
            </div>
        </div>

        <div
            class="flex items-center shrink-0"
            style="border-top: 1px solid rgba(255, 255, 255, 0.15)"
        >
            <div
                class="flex-1 flex items-center justify-center gap-2 px-3.5 py-3 cursor-pointer text-gray-500 hover:text-gray-300 transition-colors"
                @click="emit('swap')"
            >
                <PanelLeft v-if="side === 'right'" :size="14" />
                <PanelRight v-else :size="14" />
                <span class="text-[12px]">Move</span>
            </div>
            <div class="w-px h-5 bg-white/[0.15]" />
            <div
                class="flex-1 flex items-center justify-center gap-2 px-3.5 py-3 cursor-pointer text-gray-500 hover:text-gray-300 transition-colors"
                @click="emit('close')"
            >
                <PanelLeftClose v-if="side === 'left'" :size="14" />
                <PanelRightClose v-else :size="14" />
                <span class="text-[12px]">Collapse</span>
            </div>
        </div>
    </div>
</template>
