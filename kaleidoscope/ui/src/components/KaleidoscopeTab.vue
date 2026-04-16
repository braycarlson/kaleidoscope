<script setup lang="ts">
import { Wrench } from 'lucide-vue-next';
import { use_drag } from '../composables/use_drag';

const emit = defineEmits<{
    open: [];
}>();

const { tab_top, dragging, on_mousedown, on_touchstart } = use_drag(function() {
    emit('open');
});
</script>

<template>
    <div
        class="fixed right-0 z-[1000000] bg-[#12121e] border border-r-0 border-white/[0.15] rounded-l-md px-3 py-3 select-none flex flex-col items-center gap-1"
        :class="dragging ? 'cursor-grabbing opacity-80' : 'cursor-grab'"
        :style="{ top: tab_top + 'px' }"
        @mousedown="on_mousedown"
        @touchstart="on_touchstart"
    >
        <Wrench :size="14" class="opacity-50" />
    </div>
</template>
