<script setup lang="ts">
import { ref, computed, h } from 'vue';
import { Search } from 'lucide-vue-next';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import DataTable from '../DataTable.vue';
import type { ColumnDef } from '@tanstack/vue-table';

interface TemplateEntry {
    _index: number;
    context_keys: string[];
    duration_ms: number;
    name: string;
}

interface TemplateRaw {
    context_keys: string[];
    duration_ms: number;
    name: string;
}

interface TemplatesPanelData {
    count: number;
    templates: TemplateRaw[];
    total_time: number;
}

const props = defineProps<{
    data: TemplatesPanelData;
}>();

const text_filter = ref('');

const templates_enriched = computed(function(): TemplateEntry[] {
    return (props.data.templates || []).map(function(template, index) {
        return { ...template, _index: index };
    });
});

const templates_filtered = computed(function(): TemplateEntry[] {
    const search = text_filter.value.toLowerCase();

    if (!search) return templates_enriched.value;

    return templates_enriched.value.filter(function(template) {
        return template.name.toLowerCase().includes(search);
    });
});

const columns: ColumnDef<TemplateEntry, unknown>[] = [
    {
        accessorKey: '_index',
        header: '#',
        meta: { headerClass: '!w-10 hidden sm:table-cell', cellClass: 'w-10 opacity-30 hidden sm:table-cell' },
        cell: function(info) { return (info.getValue() as number) + 1; },
    },
    {
        accessorKey: 'name',
        header: 'Template',
        cell: function(info) {
            const name = info.getValue() as string;
            const is_inline = name === '<inline>';
            return h('span', {
                class: [
                    'font-mono text-[12px] overflow-hidden text-ellipsis whitespace-nowrap block max-w-[150px] sm:max-w-none',
                    is_inline ? 'opacity-40 italic' : '',
                ],
                title: name,
            }, name);
        },
    },
    {
        accessorKey: 'duration_ms',
        header: 'Duration',
        meta: { headerClass: '!w-24', cellClass: 'w-24' },
        cell: function(info) {
            const value = info.getValue() as number;
            const class_name = value >= 10 ? 'text-orange-500 font-semibold' : value >= 5 ? 'text-yellow-500' : '';
            return h('span', { class: class_name }, value.toFixed(2) + ' ms');
        },
    },
    {
        accessorKey: 'context_keys',
        header: 'Context',
        enableSorting: false,
        meta: { headerClass: '!w-20 hidden sm:table-cell', cellClass: 'w-20 hidden sm:table-cell' },
        cell: function(info) {
            const keys = info.getValue() as string[];
            return h('span', { class: keys.length > 0 ? '' : 'opacity-30' }, String(keys.length));
        },
    },
];
</script>

<template>
    <div>
        <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-5 border-b border-white/[0.08]">
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Templates</span>
                <span class="font-semibold text-[15px]">{{ data.count }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Time</span>
                <span class="font-semibold text-[15px]">{{ data.total_time }} ms</span>
            </div>
        </div>

        <CollapsibleSection
            v-if="templates_enriched.length"
            title="Templates"
            :count="data.count"
            :value_copy="data.templates"
        >
            <div class="mb-4 pl-2">
                <div class="w-full sm:w-auto relative flex items-center">
                    <Search :size="14" class="absolute left-2.5 opacity-30" />
                    <input
                        v-model="text_filter"
                        type="text"
                        placeholder="Filter templates..."
                        class="pl-8 pr-3 py-1 bg-white/[0.05] border border-white/10 rounded text-[13px] text-[#d0d0e0] outline-none focus:border-purple-500/50 w-full sm:w-64"
                    >
                </div>
            </div>

            <DataTable
                :columns="columns"
                :data="templates_filtered"
                :sorting_default="[{ id: 'duration_ms', desc: true }]"
                expandable
                width_minimum="400px"
            >
                <template #expanded="{ row }">
                    <div v-if="row.context_keys.length" class="pt-2">
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-[11px] opacity-30">Context Keys</span>
                            <CopyButton :value="row.context_keys.join(', ')" :size="11" />
                        </div>
                        <div class="flex flex-wrap gap-2">
                            <span
                                v-for="key in row.context_keys"
                                :key="key"
                                class="inline-block px-2 py-0.5 bg-white/[0.05] rounded text-[12px] font-mono text-gray-300"
                            >{{ key }}</span>
                        </div>
                    </div>
                    <div v-else class="pt-2 text-[11px] opacity-30">No context variables</div>
                </template>
            </DataTable>
        </CollapsibleSection>
        <div v-else class="py-10 text-center opacity-30 italic">No templates rendered</div>
    </div>
</template>
