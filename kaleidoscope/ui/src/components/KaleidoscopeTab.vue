<script setup lang="ts">
import { use_drag } from '../composables/use_drag';
import type { KaleidoscopeSide } from '../types';

withDefaults(defineProps<{
    side?: KaleidoscopeSide;
}>(), {
    side: 'right',
});

const emit = defineEmits<{
    open: [];
}>();

const { tab_top, dragging, on_mousedown, on_touchstart } = use_drag(function() {
    emit('open');
});
</script>

<template>
    <div
        class="fixed z-[1000000] bg-ks-panel border border-ks-tab shadow-ks-tab px-4 py-5 select-none flex flex-col items-center gap-1"
        :class="[
            dragging ? 'cursor-grabbing opacity-80' : 'cursor-grab opacity-75 hover:opacity-100',
            side === 'right'
                ? 'right-0 rounded-l-md border-r-0'
                : 'left-0 rounded-r-md border-l-0',
        ]"
        :style="{ top: tab_top + 'px' }"
        @mousedown="on_mousedown"
        @touchstart="on_touchstart"
    >
        <span class="font-bold text-[15px] tracking-[0.15em] bg-gradient-to-r from-purple-500 via-fuchsia-400 to-purple-300 bg-clip-text text-transparent">dk</span>
    </div>
</template>
