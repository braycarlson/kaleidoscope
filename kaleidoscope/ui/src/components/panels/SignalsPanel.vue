<script setup lang="ts">
import { ref, computed, h } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import DataTable from '../DataTable.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
import type { TableColumn } from '../../services/table';
import type { StackFrame } from '../../types';

interface SignalEntry {
    module: string;
    name: string;
    receiver_count: number;
    receivers: { module: string; name: string; path: string }[];
}

interface SendEntry {
    count: number;
    duration_ms: number;
    errors: number;
    module: string;
    name: string;
    receivers: string[];
    sender: string;
    site: StackFrame | null;
}

interface SignalsPanelData {
    count: number;
    send_count: number;
    send_time: number;
    sends: SendEntry[];
    signals: SignalEntry[];
    total_receivers: number;
}

const props = defineProps<{
    data: SignalsPanelData;
}>();

const text_filter = ref('');
const text_filter_sends = ref('');

const signals = computed(function(): SignalEntry[] {
    return props.data.signals;
});

const signals_filtered = computed(function(): SignalEntry[] {
    const search = text_filter.value.toLowerCase();

    if (!search) return signals.value;

    return signals.value.filter(function(signal) {
        return signal.name.toLowerCase().includes(search)
            || signal.module.toLowerCase().includes(search);
    });
});

const sends_filtered = computed(function(): SendEntry[] {
    const search = text_filter_sends.value.toLowerCase();

    if (!search) return props.data.sends;

    return props.data.sends.filter(function(send) {
        return send.name.toLowerCase().includes(search)
            || send.sender.toLowerCase().includes(search);
    });
});

const stats_header = computed(function() {
    if (!Number.isFinite(props.data.send_time)) {
        throw new RangeError('a send time must be a finite number: ' + props.data.send_time);
    }

    return [
        { label: 'Sends', value: props.data.send_count },
        { label: 'Send Time', value: props.data.send_time + ' ms' },
        { label: 'Signals', value: props.data.count },
        { label: 'Receivers', value: props.data.total_receivers },
    ];
});

function number_finite(value: unknown, noun: string): number {
    if (typeof value !== 'number') {
        throw new RangeError('a ' + noun + ' must be finite: ' + String(value));
    }

    if (!Number.isFinite(value)) throw new RangeError('a ' + noun + ' must be finite: ' + value);
    return value;
}

const columns: TableColumn<SignalEntry>[] = [
    {
        accessorKey: 'name',
        header: 'Signal',
        cell: function(info) {
            const row = info.row.original;
            const name = info.getValue() as string;

            if (typeof name !== 'string') {
                throw new TypeError('a signal name must be text: ' + String(name));
            }

            return h('span', { class: 'font-semibold' }, [
                name,
                row.receivers.length > 0
                    ? h('span', { class: 'ml-2 opacity-30 text-[11px]' }, '(' + row.receivers.length + ')')
                    : null,
            ]);
        },
    },
    {
        accessorKey: 'receiver_count',
        header: 'Receivers',
        meta: { headerClass: 'w-24!', cellClass: 'w-24' },
        cell: function(info) {
            const v = info.getValue() as number;
            if (!Number.isFinite(v)) throw new RangeError('a receiver count must be finite: ' + v);
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

const columns_sends: TableColumn<SendEntry>[] = [
    {
        accessorKey: 'name',
        header: 'Signal',
        cell: function(info) {
            const row = info.row.original;
            const name = info.getValue() as string;

            if (typeof name !== 'string') {
                throw new TypeError('a sent signal name must be text: ' + String(name));
            }

            return h('span', { class: 'font-semibold', title: row.module }, name);
        },
    },
    {
        accessorKey: 'sender',
        header: 'Sender',
        meta: {
            headerClass: 'hidden sm:table-cell',
            cellClass: 'font-mono opacity-50 overflow-hidden text-ellipsis whitespace-nowrap hidden sm:table-cell',
        },
    },
    {
        accessorKey: 'count',
        header: 'Sends',
        meta: { headerClass: 'w-20!', cellClass: 'w-20' },
        cell: function(info) {
            return number_finite(info.getValue(), 'send count');
        },
    },
    {
        accessorKey: 'duration_ms',
        header: 'Time',
        meta: { headerClass: 'w-24!', cellClass: 'w-24' },
        cell: function(info) {
            const value = number_finite(info.getValue(), 'send time');
            const class_name = value >= 10 ? 'text-orange-500 font-semibold' : '';

            return h('span', { class: class_name }, value.toFixed(2) + ' ms');
        },
    },
    {
        accessorKey: 'errors',
        header: 'Errors',
        meta: { headerClass: 'w-20!', cellClass: 'w-20' },
        cell: function(info) {
            const value = number_finite(info.getValue(), 'send error count');
            const class_name = value > 0 ? 'text-red-500 font-semibold' : 'opacity-30';

            return h('span', { class: class_name }, value);
        },
    },
];
</script>

<template>
    <div>
        <PanelHeader :stats="stats_header" />

        <CollapsibleSection
            v-if="data.sends.length"
            title="Sent"
            :count="data.send_count"
            :value_copy="data.sends"
        >
            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter_sends" placeholder="Filter..." />
            </div>

            <DataTable
                :columns="columns_sends"
                :data="sends_filtered"
                expandable
                width_minimum="300px"
            >
                <template #expanded="{ row }">
                    <div class="pt-2">
                        <div v-if="row.site" data-ks="send-site" class="mb-3">
                            <div class="text-[11px] opacity-30 mb-1">Sent from</div>
                            <div class="font-mono text-[12px] text-blue-400 break-all">{{ row.site.file }}:{{ row.site.line }}</div>
                            <div v-if="row.site.text" class="font-mono text-[11px] text-ks-muted mt-0.5 pl-2 border-l-2 border-ks-section break-all">{{ row.site.text }}</div>
                        </div>
                        <div v-if="row.receivers.length">
                            <div class="flex items-center justify-between mb-2">
                                <span class="text-[11px] opacity-30">Receivers</span>
                                <CopyButton :value="row.receivers" :size="11" />
                            </div>
                            <table class="w-full border-collapse">
                                <tbody>
                                    <tr v-for="(receiver, i) in row.receivers" :key="i" class="hover:bg-white/2">
                                        <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ receiver }}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        <div v-else class="text-[11px] opacity-30">No receivers ran</div>
                    </div>
                </template>
            </DataTable>
        </CollapsibleSection>

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
                                <tr v-for="(r, i) in row.receivers" :key="i" class="hover:bg-white/2">
                                    <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ r.path }}</td>
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
