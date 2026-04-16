<script setup lang="ts">
import { ref, computed, h } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import DataTable from '../DataTable.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
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

const text_filter = ref('');

const signals = computed(function(): SignalEntry[] {
    return props.data.signals || [];
});

const signals_filtered = computed(function(): SignalEntry[] {
    const search = text_filter.value.toLowerCase();

    if (!search) return signals.value;

    return signals.value.filter(function(signal) {
        return signal.name.toLowerCase().includes(search)
            || signal.module.toLowerCase().includes(search);
    });
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
        <PanelHeader
            :stats="[
                { label: 'Signals', value: data.count },
                { label: 'Receivers', value: data.total_receivers },
            ]"
        />

        <CollapsibleSection
            title="Signals"
            :count="data.count"
            :value_copy="data.signals"
        >
            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter" placeholder="Filter..." />
            </div>

            <DataTable
                :columns="columns"
                :data="signals_filtered"
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
