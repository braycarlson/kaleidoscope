import { ref, computed, type Ref, type ComputedRef } from 'vue';
import type { SortDirection } from '../types';

interface UseSortReturn<T> {
    sort_column: Ref<string | null>;
    sort_direction: Ref<SortDirection>;
    sorted: ComputedRef<T[]>;
    sort_toggle: (column: string) => void;
}

export function compare_sort_values(a: unknown, b: unknown): number {
    const va = a ?? '';
    const vb = b ?? '';

    if (typeof va === 'number' && typeof vb === 'number') return va - vb;

    const sa = String(va).toLowerCase();
    const sb = String(vb).toLowerCase();

    if (sa < sb) return -1;
    if (sa > sb) return 1;
    return 0;
}

export function use_sort<T extends object>(
    items_ref: Ref<T[]> | ComputedRef<T[]>,
    column_default: string | null,
    direction_default: SortDirection,
): UseSortReturn<T> {
    const sort_column = ref<string | null>(column_default);
    const sort_direction = ref<SortDirection>(direction_default);

    const sorted = computed(function() {
        const list = items_ref.value;
        const column = sort_column.value;

        if (!list || !column) return list;

        return list.slice().sort(function(a, b) {
            const row_a = a as Record<string, unknown>;
            const row_b = b as Record<string, unknown>;
            const result = compare_sort_values(row_a[column], row_b[column]);
            return sort_direction.value === 'asc' ? result : -result;
        });
    });

    function sort_toggle(column: string) {
        if (sort_column.value === column) {
            sort_direction.value = sort_direction.value === 'asc' ? 'desc' : 'asc';
        } else {
            sort_column.value = column;
            sort_direction.value = 'asc';
        }
    }

    return { sort_column, sort_direction, sorted, sort_toggle };
}
