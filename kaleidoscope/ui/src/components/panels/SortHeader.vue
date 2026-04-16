<script setup lang="ts">
import { ArrowUp, ArrowDown } from 'lucide-vue-next';
import type { SortDirection } from '../../types';

defineProps<{
    column: string;
    sort_column?: string | null;
    sort_direction?: SortDirection;
    label: string;
}>();

const emit = defineEmits<{
    sort: [column: string];
}>();
</script>

<template>
    <th
        class="px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/[0.08] cursor-pointer hover:opacity-70 whitespace-nowrap select-none"
        @click="emit('sort', column)"
    >
        <span class="flex items-center gap-1">
            {{ label }}
            <ArrowUp v-if="sort_column === column && sort_direction === 'asc'" :size="10" />
            <ArrowDown v-else-if="sort_column === column && sort_direction === 'desc'" :size="10" />
        </span>
    </th>
</template>
