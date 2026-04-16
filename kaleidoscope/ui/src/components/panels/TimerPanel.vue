<script setup lang="ts">
import { computed } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import DataTable from '../DataTable.vue';
import type { ColumnDef } from '@tanstack/vue-table';

interface TimerRow {
    field: string;
    value: string | number;
}

interface TimerPanelData {
    asgi: boolean;
    content_type: string;
    method: string;
    path: string;
    status_code: number;
    total_ms: number;
}

const props = defineProps<{
    data: TimerPanelData;
}>();

const rows = computed(function(): TimerRow[] {
    if (!props.data.total_ms) return [];

    return [
        { field: 'Server', value: props.data.asgi ? 'ASGI' : 'WSGI' },
        { field: 'Method', value: props.data.method },
        { field: 'Path', value: props.data.path },
        { field: 'Status Code', value: props.data.status_code },
        { field: 'Content Type', value: props.data.content_type },
        { field: 'Total Time', value: props.data.total_ms + ' ms' },
    ];
});

const columns: ColumnDef<TimerRow, unknown>[] = [
    {
        accessorKey: 'field',
        header: 'Field',
        enableSorting: false,
        meta: { headerClass: '!w-32 sm:!w-48', cellClass: 'w-32 sm:w-48 opacity-50 font-semibold' },
    },
    {
        accessorKey: 'value',
        header: 'Value',
        enableSorting: false,
        meta: { cellClass: 'font-mono break-all' },
    },
];
</script>

<template>
    <div>
        <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-5 border-b border-white/[0.08]">
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Total</span>
                <span class="font-semibold text-[15px]">{{ data.total_ms }} ms</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Status</span>
                <span class="font-semibold text-[15px]" :class="data.status_code >= 400 ? 'text-red-500' : 'text-green-500'">{{ data.status_code }}</span>
            </div>
        </div>

        <CollapsibleSection
            v-if="rows.length"
            title="Request Details"
            :value_copy="data"
        >
            <DataTable
                :columns="columns"
                :data="rows"
                width_minimum="300px"
            />
        </CollapsibleSection>
        <div v-else class="py-10 text-center opacity-30 italic">No request captured</div>
    </div>
</template>
