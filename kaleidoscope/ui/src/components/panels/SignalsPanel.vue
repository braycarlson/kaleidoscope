<script setup lang="ts">
import { computed, h } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import DataTable from '../DataTable.vue';
import type { ColumnDef } from '@tanstack/vue-table';

interface SignalEntry {
    module: string;
    name: string;
    receiver_count: number;
    receivers: { module: string; name: string; path: string }[];
}

interface SignalsPanelData {
    count: number;
    signals: SignalEntry[];
    total_receivers: number;
}

const props = defineProps<{
    data: SignalsPanelData;
}>();

const signals = computed(function(): SignalEntry[] {
    return props.data.signals || [];
});

const columns: ColumnDef<SignalEntry, unknown>[] = [
    {
        accessorKey: 'name',
        header: 'Signal',
        cell: function(info) {
            const row = info.row.original;
            return h('span', { class: 'font-semibold' }, [
                info.getValue() as string,
                row.receivers.length > 0
                    ? h('span', { class: 'ml-2 opacity-30 text-[11px]' }, '(' + row.receivers.length + ')')
                    : null,
            ]);
        },
    },
    {
        accessorKey: 'receiver_count',
        header: 'Receivers',
        meta: { headerClass: '!w-24', cellClass: 'w-24' },
        cell: function(info) {
            const v = info.getValue() as number;
            return h('span', { class: v > 0 ? 'text-green-500' : 'opacity-30' }, v);
        },
    },
    {
        accessorKey: 'module',
        header: 'Module',
        meta: {
            headerClass: 'hidden sm:table-cell',
            cellClass: 'font-mono opacity-50 overflow-hidden text-ellipsis whitespace-nowrap hidden sm:table-cell',
        },
    },
];
</script>

<template>
    <div>
        <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-5 border-b border-white/[0.08]">
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Signals</span>
                <span class="font-semibold text-[15px]">{{ data.count }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Receivers</span>
                <span class="font-semibold text-[15px]">{{ data.total_receivers }}</span>
            </div>
        </div>

        <CollapsibleSection
            title="Signals"
            :count="data.count"
            :value_copy="data.signals"
        >
            <DataTable
                :columns="columns"
                :data="signals"
                expandable
                width_minimum="300px"
            >
                <template #expanded="{ row }">
                    <div v-if="row.receivers.length" class="pt-2">
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-[11px] opacity-30">Receivers</span>
                            <CopyButton :value="row.receivers" :size="11" />
                        </div>
                        <table class="w-full border-collapse">
                            <tbody>
                                <tr v-for="(r, i) in row.receivers" :key="i" class="hover:bg-white/[0.02]">
                                    <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ r.path }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <div v-else class="pt-2 text-[11px] opacity-30">No receivers</div>
                </template>
            </DataTable>
        </CollapsibleSection>
    </div>
</template>
