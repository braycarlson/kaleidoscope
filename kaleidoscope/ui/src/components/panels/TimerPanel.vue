<script setup lang="ts">
import { computed } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import DataTable from '../DataTable.vue';
import PanelHeader from '../PanelHeader.vue';
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
        <PanelHeader
            :stats="[
                { label: 'Total', value: data.total_ms + ' ms' },
                { label: 'Status', value: data.status_code },
            ]"
        />

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
