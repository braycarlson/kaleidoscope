<script setup lang="ts">
import { computed, ref, onUnmounted } from 'vue';
import { Check, Copy } from 'lucide-vue-next';
import { clipboard_write } from '../services/clipboard';
import { text_resolve } from '../services/format';
import { COPY_FEEDBACK_MS } from '../constants';
import type { CopyFormat, CopyValue } from '../types';

const props = defineProps<{
    value: CopyValue;
    label?: string;
    size?: number;
    format?: CopyFormat | undefined;
}>();

const ICON_SIZE_DEFAULT = 13;

const copied = ref(false);
let id_timeout: ReturnType<typeof setTimeout> | null = null;

function copied_show() {
    copied.value = true;

    if (id_timeout) {
        clearTimeout(id_timeout);
    }

    id_timeout = setTimeout(function() {
        copied.value = false;
        id_timeout = null;
    }, COPY_FEEDBACK_MS);
}

const icon_size = computed(function(): number {
    const size = props.size;

    if (size === undefined) return ICON_SIZE_DEFAULT;
    if (!Number.isFinite(size)) throw new RangeError('an icon size must be finite: ' + size);
    if (size <= 0) throw new RangeError('an icon size must be positive: ' + size);
    return size;
});

function copy() {
    const text = text_resolve(props.value, props.format);

    clipboard_write(text).then(copied_show).catch(function() {
        copied.value = false;
    });
}

onUnmounted(function() {
    if (id_timeout) {
        clearTimeout(id_timeout);
    }
});
</script>

<template>
    <button
        class="flex items-center gap-1.5 text-gray-500 hover:text-gray-300 transition-colors opacity-50 hover:opacity-100"
        :class="copied ? 'opacity-100! text-green-400!' : ''"
        :title="label || 'Copy to clipboard'"
        @click.stop="copy"
    >
        <Check v-if="copied" :size="icon_size" />
        <Copy v-else :size="icon_size" />
        <span v-if="label">{{ copied ? 'Copied' : label }}</span>
    </button>
</template>
