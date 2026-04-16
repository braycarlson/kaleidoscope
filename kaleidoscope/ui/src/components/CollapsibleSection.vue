<script setup lang="ts">
import { ref } from 'vue';
import { ChevronRight } from 'lucide-vue-next';
import CopyButton from './CopyButton.vue';
import type { CopyFormat, CopyValue } from '../types';

const props = withDefaults(defineProps<{
    title: string;
    count?: number;
    open?: boolean;
    value_copy?: CopyValue | null;
    format_copy?: CopyFormat;
}>(), {
    count: -1,
    open: true,
    value_copy: null,
    format_copy: undefined,
});

const is_open = ref(props.open);

function toggle() {
    is_open.value = !is_open.value;
}
</script>

<template>
    <div class="mb-4">
        <div class="flex items-center gap-3 mb-2">
            <div
                class="font-semibold text-[13px] cursor-pointer select-none flex items-center gap-2 hover:opacity-80"
                @click="toggle"
            >
                <ChevronRight
                    :size="14"
                    class="opacity-40 transition-transform duration-150"
                    :class="is_open ? 'rotate-90' : ''"
                />
                {{ title }}
                <span v-if="count >= 0" class="opacity-30 font-normal">({{ count }})</span>
            </div>
            <CopyButton
                v-if="value_copy !== null"
                :value="value_copy"
                :format="format_copy"
            />
            <slot name="actions" />
        </div>
        <div v-show="is_open" class="pt-3">
            <slot />
        </div>
    </div>
</template>
