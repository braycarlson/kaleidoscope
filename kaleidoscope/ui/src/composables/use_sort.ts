import { ref, computed, type Ref, type ComputedRef } from 'vue';
import type { SortDirection } from '../types';

interface UseSortReturn<T> {
    sort_column: Ref<string | null>;
    sort_direction: Ref<SortDirection>;
    sorted: ComputedRef<T[]>;
    sort_toggle: (column: string) => void;
}

function text_of(value: unknown): string {
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    if (typeof value === 'boolean') return String(value);

    const text = JSON.stringify(value) as string | undefined;

    if (text === undefined) throw new TypeError('a sort value must be JSON: ' + typeof value);

    return text;
}

function sort_rank(value: unknown): number {
    if (typeof value !== 'number') return 2;
    if (Number.isNaN(value)) return 0;
    return 1;
}

export function compare_sort_values(a: unknown, b: unknown): number {
    const va = a ?? '';
    const vb = b ?? '';
    const rank_a = sort_rank(va);
    const rank_b = sort_rank(vb);

    if (rank_a !== rank_b) return rank_a - rank_b;

    if (rank_a === 1) {
        if ((va as number) < (vb as number)) return -1;
        if ((va as number) > (vb as number)) return 1;
        return 0;
    }

    if (rank_a === 0) return 0;

    const sa = text_of(va).toLowerCase();
    const sb = text_of(vb).toLowerCase();

    if (sa < sb) return -1;
    if (sa > sb) return 1;
    return 0;
}

export function use_sort<T extends object>(
    items_ref: Ref<T[]> | ComputedRef<T[]>,
    column_default: string | null,
    direction_default: SortDirection,
): UseSortReturn<T> {
    if (column_default === '') throw new RangeError('a default sort column must not be empty');

    const sort_column = ref<string | null>(column_default);
    const sort_direction = ref<SortDirection>(direction_default);

    const sorted = computed(function() {
        const list = items_ref.value;
        const column = sort_column.value;

        if (!column) return list;

        return list.slice().sort(function(a, b) {
            const row_a = a as Record<string, unknown>;
            const row_b = b as Record<string, unknown>;
            const result = compare_sort_values(row_a[column], row_b[column]);

            return sort_direction.value === 'asc' ? result : -result;
        });
    });

    function sort_toggle(column: string) {
        if (column === '') throw new RangeError('a sort column must not be empty');

        if (sort_column.value === column) {
            sort_direction.value = sort_direction.value === 'asc' ? 'desc' : 'asc';
        } else {
            sort_column.value = column;
            sort_direction.value = 'asc';
        }
    }

    return { sort_column, sort_direction, sorted, sort_toggle };
}
