<script setup lang="ts">
import { computed, h } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import DataTable from '../DataTable.vue';
import type { ColumnDef } from '@tanstack/vue-table';

interface CacheCall {
    _index: number;
    alias: string;
    args: string;
    duration_ms: number;
    hit: boolean;
    method: string;
}

interface CachePanelData {
    calls: Omit<CacheCall, '_index'>[];
    count: number;
    hits: number;
    misses: number;
    total_time: number;
}

const props = defineProps<{
    data: CachePanelData;
}>();

const calls_enriched = computed(function(): CacheCall[] {
    return (props.data.calls || []).map(function(call, index) {
        return { ...call, _index: index };
    });
});

function class_method(method: string): string {
    if (method === 'GET' || method === 'GET_MANY' || method === 'GET_OR_SET' || method === 'HAS_KEY') return 'text-blue-400';
    if (method === 'SET' || method === 'SET_MANY' || method === 'ADD') return 'text-green-400';
    if (method === 'DELETE' || method === 'DELETE_MANY' || method === 'CLEAR') return 'text-red-400';
    if (method === 'INCR') return 'text-yellow-400';
    return '';
}

const columns: ColumnDef<CacheCall, unknown>[] = [
    {
        accessorKey: 'alias',
        header: 'Backend',
        meta: { headerClass: '!w-24', cellClass: 'w-24 opacity-50' },
    },
    {
        accessorKey: 'method',
        header: 'Method',
        meta: { headerClass: '!w-24', cellClass: 'w-24 font-semibold' },
        cell: function(info) {
            return h('span', { class: class_method(info.getValue() as string) }, info.getValue() as string);
        },
    },
    {
        accessorKey: 'duration_ms',
        header: 'Time',
        meta: { headerClass: '!w-24 hidden sm:table-cell', cellClass: 'w-24 font-mono whitespace-nowrap hidden sm:table-cell' },
        cell: function(info) {
            const value = info.getValue() as number;
            const class_name = value >= 10 ? 'text-orange-500 font-semibold' : value >= 5 ? 'text-yellow-500' : '';
            return h('span', { class: class_name }, value.toFixed(2) + ' ms');
        },
    },
    {
        accessorKey: 'hit',
        header: 'Result',
        meta: { headerClass: '!w-16 hidden sm:table-cell', cellClass: 'w-16 hidden sm:table-cell' },
        cell: function(info) {
            const row = info.row.original;
            if (row.method === 'SET' || row.method === 'SET_MANY' || row.method === 'DELETE' || row.method === 'DELETE_MANY' || row.method === 'CLEAR' || row.method === 'INCR' || row.method === 'ADD') {
                return h('span', { class: 'opacity-30' }, '-');
            }
            const hit = info.getValue() as boolean;
            return h('span', { class: hit ? 'text-green-500' : 'text-red-500' }, hit ? 'Hit' : 'Miss');
        },
    },
    {
        accessorKey: 'args',
        header: 'Key',
        meta: { cellClass: 'font-mono overflow-hidden text-ellipsis whitespace-nowrap max-w-0' },
        cell: function(info) {
            return h('span', { title: info.getValue() as string }, info.getValue() as string);
        },
    },
];
</script>

<template>
    <div>
        <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-5 border-b border-white/[0.08]">
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Calls</span>
                <span class="font-semibold text-[15px]">{{ data.count }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Hits</span>
                <span class="font-semibold text-[15px] text-green-500">{{ data.hits }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Misses</span>
                <span class="font-semibold text-[15px]" :class="data.misses > 0 ? 'text-orange-500' : ''">{{ data.misses }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Time</span>
                <span class="font-semibold text-[15px]">{{ data.total_time }} ms</span>
            </div>
        </div>

        <CollapsibleSection
            v-if="calls_enriched.length"
            title="Cache"
            :count="data.count"
            :value_copy="data.calls"
        >
            <DataTable
                :columns="columns"
                :data="calls_enriched"
                :sorting_default="[{ id: 'duration_ms', desc: true }]"
                expandable
                width_minimum="400px"
            >
                <template #expanded="{ row }">
                    <div class="pt-4 flex items-start gap-2">
                        <span class="flex-1 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{{ row.args }}</span>
                        <CopyButton :value="row.args" :size="11" />
                    </div>
                </template>
            </DataTable>
        </CollapsibleSection>
        <div v-else class="py-10 text-center opacity-30 italic">No cache calls recorded</div>
    </div>
</template>
