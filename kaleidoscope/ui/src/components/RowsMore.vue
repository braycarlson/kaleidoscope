<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
    columns: number;
    hidden_count: number;
}>();

const emit = defineEmits<{
    more: [];
}>();

const colspan = computed(function(): number {
    const columns = props.columns;

    if (!Number.isInteger(columns)) throw new TypeError('columns must be an integer: ' + columns);
    if (columns < 1) throw new RangeError('columns must be at least 1: ' + columns);
    return columns;
});

const label = computed(function(): string {
    const count = props.hidden_count;

    if (!Number.isInteger(count)) throw new TypeError('hidden_count must be an integer: ' + count);
    if (count < 1) throw new RangeError('hidden_count must be at least 1: ' + count);
    return 'Show ' + count + ' more';
});
</script>

<template>
    <tr>
        <td :colspan="colspan" class="px-2 py-2 border-t border-white/4 text-center">
            <button
                type="button"
                data-ks="rows-more"
                class="text-[12px] text-purple-400 hover:text-purple-300"
                @click.stop="emit('more')"
            >
                {{ label }}
            </button>
        </td>
    </tr>
</template>
