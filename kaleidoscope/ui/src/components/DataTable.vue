<script setup lang="ts" generic="T extends object">
import { ref, watch } from 'vue';
import { ArrowUp, ArrowDown, ChevronsUpDown } from 'lucide-vue-next';
import {
    useVueTable,
    getCoreRowModel,
    getSortedRowModel,
    FlexRender,
    type ColumnDef,
    type SortingState,
} from '@tanstack/vue-table';

const props = withDefaults(defineProps<{
    columns: ColumnDef<T, unknown>[];
    data: T[];
    sorting_default?: SortingState;
    expandable?: boolean;
    width_minimum?: string;
}>(), {
    sorting_default: () => [],
    expandable: false,
    width_minimum: '500px',
});

const emit = defineEmits<{
    'row-click': [row: T, index: number];
}>();

const expanded = ref(new Set<number>());
const sorting = ref<SortingState>([...props.sorting_default]);

watch(function() { return props.sorting_default; }, function(value) {
    if (sorting.value.length === 0) {
        sorting.value = [...value];
    }
});

watch(function() { return props.data; }, function() {
    expanded.value = new Set();
});

const table = useVueTable({
    get data() { return props.data; },
    get columns() { return props.columns; },
    state: {
        get sorting() { return sorting.value; },
    },
    onSortingChange: function(updater) {
        sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater;
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    enableSortingRemoval: false,
});

function is_expanded(index: number): boolean {
    return expanded.value.has(index);
}

function on_row_click(row: T, index: number) {
    if (props.expandable) {
        const next = new Set(expanded.value);

        if (next.has(index)) {
            next.delete(index);
        } else {
            next.add(index);
        }

        expanded.value = next;
    }

    emit('row-click', row, index);
}

function column_count(): number {
    return table.getHeaderGroups()[0].headers.length;
}
</script>

<template>
    <div class="overflow-x-auto -mx-3 px-3 sm:-mx-5 sm:px-5 md:mx-0 md:px-0">
        <table class="w-full border-collapse" :style="{ minWidth: width_minimum }">
            <thead>
                <tr>
                    <th
                        v-for="header in table.getHeaderGroups()[0].headers"
                        :key="header.id"
                        class="px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/[0.08] select-none whitespace-nowrap"
                        :class="[
                            header.column.getCanSort() ? 'cursor-pointer hover:opacity-70' : '',
                            (header.column.columnDef.meta as Record<string, string> | undefined)?.headerClass || '',
                        ]"
                        @click="header.column.getToggleSortingHandler()?.($event)"
                    >
                        <span class="flex items-center gap-1">
                            <FlexRender
                                :render="header.column.columnDef.header"
                                :props="header.getContext()"
                            />
                            <template v-if="header.column.getCanSort()">
                                <ArrowUp v-if="header.column.getIsSorted() === 'asc'" :size="10" />
                                <ArrowDown v-else-if="header.column.getIsSorted() === 'desc'" :size="10" />
                                <ChevronsUpDown v-else :size="10" class="opacity-30" />
                            </template>
                        </span>
                    </th>
                </tr>
            </thead>
            <tbody>
                <template v-for="row in table.getRowModel().rows" :key="row.id">
                    <tr
                        class="hover:bg-white/[0.03]"
                        :class="[expandable ? 'cursor-pointer' : '']"
                        @click="on_row_click(row.original, row.index)"
                    >
                        <td
                            v-for="cell in row.getVisibleCells()"
                            :key="cell.id"
                            class="px-2 py-2 text-[13px] border-b border-white/[0.04]"
                            :class="(cell.column.columnDef.meta as Record<string, string> | undefined)?.cellClass || ''"
                        >
                            <FlexRender
                                :render="cell.column.columnDef.cell"
                                :props="cell.getContext()"
                            />
                        </td>
                    </tr>
                    <tr v-if="expandable && is_expanded(row.index)">
                        <td
                            :colspan="column_count()"
                            class="!p-0 !px-2.5 !pb-4 border-b border-white/[0.06]"
                        >
                            <slot name="expanded" :row="row.original" :index="row.index" />
                        </td>
                    </tr>
                </template>
            </tbody>
        </table>
    </div>
</template>
