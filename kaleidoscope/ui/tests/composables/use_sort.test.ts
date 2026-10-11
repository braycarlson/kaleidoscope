import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import { compare_sort_values, use_sort } from '../../src/composables/use_sort';

describe('compare_sort_values', function() {
    it('compares numbers numerically', function() {
        expect(compare_sort_values(2, 10)).toBeLessThan(0);
        expect(compare_sort_values(10, 2)).toBeGreaterThan(0);
        expect(compare_sort_values(3, 3)).toBe(0);
    });

    it('compares text case-insensitively', function() {
        expect(compare_sort_values('alpha', 'Beta')).toBeLessThan(0);
        expect(compare_sort_values('GET', 'get')).toBe(0);
    });

    it('treats null and undefined as empty text', function() {
        expect(compare_sort_values(null, '')).toBe(0);
        expect(compare_sort_values(undefined, 'a')).toBeLessThan(0);
    });

    it('orders every number before any text so mixed columns sort consistently', function() {
        const values: unknown[] = ['9', 10, 9, 2, 'apple', null];
        const sorted = values.slice().sort(compare_sort_values);

        expect(sorted).toEqual([2, 9, 10, null, '9', 'apple']);
    });

    it('treats infinities as numbers and NaN as smallest without breaking the order', function() {
        const values: unknown[] = [Infinity, NaN, -Infinity, 0, Infinity];
        const sorted = values.slice().sort(compare_sort_values);

        expect(sorted).toEqual([NaN, -Infinity, 0, Infinity, Infinity]);
        expect(compare_sort_values(Infinity, Infinity)).toBe(0);
        expect(compare_sort_values(NaN, NaN)).toBe(0);
    });
});

describe('use_sort', function() {
    const rows = [
        { name: 'b', time: 3 },
        { name: 'a', time: 10 },
        { name: 'c', time: 1 },
    ];

    it('sorts by the default column and direction', function() {
        const items = ref(rows);
        const { sorted } = use_sort(items, 'time', 'desc');

        expect(sorted.value.map(function(row) { return row.time; })).toEqual([10, 3, 1]);
    });

    it('flips the direction when the same column is toggled', function() {
        const items = ref(rows);
        const { sort_direction, sort_toggle, sorted } = use_sort(items, 'time', 'desc');

        sort_toggle('time');

        expect(sort_direction.value).toBe('asc');
        expect(sorted.value.map(function(row) { return row.time; })).toEqual([1, 3, 10]);
    });

    it('starts a new column ascending', function() {
        const items = ref(rows);

        const {
            sort_column,
            sort_direction,
            sort_toggle,
            sorted,
        } = use_sort(items, 'time', 'desc');

        sort_toggle('name');

        expect(sort_column.value).toBe('name');
        expect(sort_direction.value).toBe('asc');
        expect(sorted.value.map(function(row) { return row.name; })).toEqual(['a', 'b', 'c']);
    });

    it('leaves the list alone without a column and never mutates the source', function() {
        const items = ref(rows.slice());
        const { sorted } = use_sort(items, null, 'asc');

        expect(sorted.value).toBe(items.value);

        const keyed = use_sort(items, 'time', 'asc');

        expect(keyed.sorted.value).not.toBe(items.value);
        expect(items.value.map(function(row) { return row.name; })).toEqual(['b', 'a', 'c']);
    });

    it('follows changes to the source list', function() {
        const items = ref(rows.slice());
        const { sorted } = use_sort(items, 'time', 'asc');

        items.value = [...items.value, { name: 'd', time: 0 }];

        expect(sorted.value[0]?.name).toBe('d');
    });
});

describe('compare_sort_values over structured values', function() {
    it('compares objects and lists by their JSON text', function() {
        expect(compare_sort_values({ a: 1 }, { b: 1 })).toBe(-1);
        expect(compare_sort_values([2], [1])).toBe(1);
        expect(compare_sort_values(true, 'true')).toBe(0);
    });
});

describe('use_sort contracts', function() {
    it('refuses an empty column as the default or as a toggle', function() {
        const items = ref([{ name: 'a' }]);

        expect(function() { use_sort(items, '', 'asc'); }).toThrow(RangeError);

        const { sort_toggle } = use_sort(items, 'name', 'asc');

        expect(function() { sort_toggle(''); }).toThrow(RangeError);
    });

    it('refuses a sort value that has no JSON form', function() {
        function compare_function_value(): number {
            return compare_sort_values(compare_function_value, 'a');
        }

        expect(compare_function_value).toThrow('a sort value must be JSON: function');
    });
});

