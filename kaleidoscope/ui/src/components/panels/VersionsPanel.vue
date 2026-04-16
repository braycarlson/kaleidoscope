<script setup lang="ts">
import { ref, computed, h } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import DataTable from '../DataTable.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
import type { ColumnDef } from '@tanstack/vue-table';

interface PackageEntry {
    description: string;
    name: string;
    version: string;
}

interface VersionsPanelData {
    count: number;
    django: string;
    packages: PackageEntry[];
    python: string;
}

const props = defineProps<{
    data: VersionsPanelData;
}>();

const text_filter = ref('');

const packages_filtered = computed(function(): PackageEntry[] {
    const search = text_filter.value.toLowerCase();
    const packages: PackageEntry[] = props.data.packages || [];

    if (!search) return packages;

    return packages.filter(function(p) {
        return p.name.toLowerCase().includes(search) || p.version.toLowerCase().includes(search) || p.description.toLowerCase().includes(search);
    });
});

const columns: ColumnDef<PackageEntry, unknown>[] = [
    {
        accessorKey: 'name',
        header: 'Package',
        meta: { headerClass: '!w-48 sm:!w-72', cellClass: 'w-48 sm:w-72 font-semibold' },
    },
    {
        accessorKey: 'version',
        header: 'Version',
        meta: { headerClass: '!w-24 sm:!w-32', cellClass: 'font-mono opacity-60' },
    },
    {
        accessorKey: 'description',
        header: 'Description',
        meta: { cellClass: 'opacity-40 overflow-hidden text-ellipsis whitespace-nowrap' },
        cell: function(info) {
            const value = info.getValue() as string;
            return h('span', { title: value }, value);
        },
    },
];
</script>

<template>
    <div>
        <PanelHeader
            :stats="[
                { label: 'Python', value: data.python },
                { label: 'Django', value: data.django },
                { label: 'Packages', value: data.count },
            ]"
        />

        <CollapsibleSection
            title="Installed Packages"
            :count="data.count"
            :value_copy="data.packages"
        >
            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter" />
            </div>

            <DataTable
                :columns="columns"
                :data="packages_filtered"
                :sorting_default="[{ id: 'name', desc: false }]"
                width_minimum="350px"
            />
        </CollapsibleSection>
    </div>
</template>
