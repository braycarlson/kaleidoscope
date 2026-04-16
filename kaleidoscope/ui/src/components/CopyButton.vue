<script setup lang="ts">
import { ref, onUnmounted } from 'vue';
import { Check, Copy } from 'lucide-vue-next';
import { text_resolve } from '../services/format';
import { COPY_FEEDBACK_MS } from '../constants';
import type { CopyFormat, CopyValue } from '../types';

const props = defineProps<{
    value: CopyValue;
    label?: string;
    size?: number;
    format?: CopyFormat;
}>();

const copied = ref(false);
let id_timeout: ReturnType<typeof setTimeout> | null = null;

function copy() {
    const text = text_resolve(props.value, props.format);

    navigator.clipboard.writeText(text).then(function() {
        copied.value = true;

        if (id_timeout) clearTimeout(id_timeout);

        id_timeout = setTimeout(function() {
            copied.value = false;
            id_timeout = null;
        }, COPY_FEEDBACK_MS);
    });
}

onUnmounted(function() {
    if (id_timeout) clearTimeout(id_timeout);
});
</script>

<template>
    <button
        class="flex items-center gap-1.5 text-gray-500 hover:text-gray-300 transition-colors opacity-50 hover:opacity-100"
        :class="copied ? '!opacity-100 !text-green-400' : ''"
        :title="label || 'Copy to clipboard'"
        @click.stop="copy"
    >
        <Check v-if="copied" :size="size || 13" />
        <Copy v-else :size="size || 13" />
        <span v-if="label">{{ copied ? 'Copied' : label }}</span>
    </button>
</template>
