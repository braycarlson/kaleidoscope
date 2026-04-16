<script setup lang="ts">
import { Wrench } from 'lucide-vue-next';
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
        class="fixed z-[1000000] bg-[#12121e] border border-white/[0.15] px-3 py-3 select-none flex flex-col items-center gap-1"
        :class="[
            dragging ? 'cursor-grabbing opacity-80' : 'cursor-grab',
            side === 'right'
                ? 'right-0 rounded-l-md border-r-0'
                : 'left-0 rounded-r-md border-l-0',
        ]"
        :style="{ top: tab_top + 'px' }"
        @mousedown="on_mousedown"
        @touchstart="on_touchstart"
    >
        <Wrench :size="14" class="opacity-50" />
    </div>
</template>
