import {
    createSortedRowModel,
    rowSortingFeature,
    sortFn_alphanumeric,
    sortFn_basic,
    sortFn_datetime,
    tableFeatures,
    type ColumnDef,
    type RowData,
} from '@tanstack/vue-table';
import { ROWS_VISIBLE_MAX } from '../constants';

export const TABLE_FEATURES = tableFeatures({
    rowSortingFeature,
    sortedRowModel: createSortedRowModel(),
    sortFns: {
        alphanumeric: sortFn_alphanumeric,
        basic: sortFn_basic,
        datetime: sortFn_datetime,
    },
});

export type TableFeatures = typeof TABLE_FEATURES;
export type TableColumn<T extends RowData> = ColumnDef<TableFeatures, T>;

export function rows_hidden_count(rows: readonly unknown[], complete: boolean): number {
    if (complete) return 0;

    return Math.max(0, rows.length - ROWS_VISIBLE_MAX);
}

export function rows_visible<T>(rows: readonly T[], complete: boolean): readonly T[] {
    if (complete) return rows;

    return rows.slice(0, ROWS_VISIBLE_MAX);
}
