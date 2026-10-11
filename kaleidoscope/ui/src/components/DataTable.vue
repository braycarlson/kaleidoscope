<script setup lang="ts" generic="T extends object">
import { computed, ref, watch } from 'vue';
import { ArrowUp, ArrowDown, ChevronsUpDown } from 'lucide-vue-next';
import { FlexRender, useTable, type SortingState } from '@tanstack/vue-table';
import {
    TABLE_FEATURES,
    rows_hidden_count,
    rows_visible,
    type TableColumn,
} from '../services/table';
import RowsMore from './RowsMore.vue';

const props = withDefaults(defineProps<{
    columns: TableColumn<T>[];
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

interface ColumnClasses {
    cellClass?: string;
    headerClass?: string;
}

const expanded = ref(new Set<number>());
const rows_complete = ref(false);
const sorting = ref<SortingState>([...props.sorting_default]);

watch(function() { return props.sorting_default; }, function(value) {
    if (sorting.value.length === 0) {
        sorting.value = [...value];
    }
});

watch(function() { return props.data.length; }, function(length_new, length_old) {
    if (length_new !== length_old) {
        expanded.value = new Set();
    }
});

const table = useTable({
    features: TABLE_FEATURES,
    get data() { return props.data; },
    get columns() { return props.columns; },
    state: {
        get sorting() { return sorting.value; },
    },
    onSortingChange: function(updater) {
        sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater;
    },
    enableSortingRemoval: false,
});

function classes_of(meta: object | undefined): ColumnClasses {
    return meta ?? {};
}

function index_validate(index: number) {
    if (!Number.isInteger(index)) throw new TypeError('a row index must be an integer: ' + index);
    if (index < 0) throw new RangeError('a row index must not be negative: ' + index);

    if (index >= props.data.length) {
        throw new RangeError('a row index must be below ' + props.data.length + ': ' + index);
    }
}

function is_expanded(index: number): boolean {
    index_validate(index);

    return expanded.value.has(index);
}

function on_row_click(row: T, index: number) {
    index_validate(index);

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

const headers = computed(function() {
    if (props.columns.length < 1) throw new RangeError('a data table needs at least one column');

    return table.getHeaderGroups()[0]?.headers ?? [];
});

const rows = computed(function() {
    return table.getRowModel().rows;
});

function column_count(): number {
    return headers.value.length;
}
</script>

<template>
    <div class="overflow-x-auto -mx-3 px-3 sm:-mx-5 sm:px-5 md:mx-0 md:px-0">
        <table class="w-full border-collapse" :style="{ minWidth: width_minimum }">
            <thead>
                <tr>
                    <th
                        v-for="header in headers"
                        :key="header.id"
                        class="px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/8 select-none whitespace-nowrap"
                        :class="[
                            header.column.getCanSort() ? 'cursor-pointer hover:opacity-70' : '',
                            classes_of(header.column.columnDef.meta).headerClass ?? '',
                        ]"
                        @click="header.column.getToggleSortingHandler()?.($event)"
                    >
                        <span class="flex items-center gap-1">
                            <FlexRender :header="header" />
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
                <template v-for="row in rows_visible(rows, rows_complete)" :key="row.id">
                    <tr
                        class="hover:bg-white/3"
                        :class="[expandable ? 'cursor-pointer' : '']"
                        @click="on_row_click(row.original, row.index)"
                    >
                        <td
                            v-for="cell in row.getAllCells()"
                            :key="cell.id"
                            class="px-2 py-2 text-[13px] border-b border-white/4"
                            :class="classes_of(cell.column.columnDef.meta).cellClass ?? ''"
                        >
                            <FlexRender :cell="cell" />
                        </td>
                    </tr>
                    <tr v-if="expandable && is_expanded(row.index)">
                        <td
                            :colspan="column_count()"
                            class="p-0! px-2.5! pb-4! border-b border-white/6"
                        >
                            <slot name="expanded" :row="row.original" :index="row.index" />
                        </td>
                    </tr>
                </template>
                <RowsMore
                    v-if="rows_hidden_count(rows, rows_complete) > 0"
                    :columns="column_count()"
                    :hidden_count="rows_hidden_count(rows, rows_complete)"
                    @more="rows_complete = true"
                />
            </tbody>
        </table>
    </div>
</template>
