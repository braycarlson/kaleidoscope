import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { compare_sort_values } from '../../src/composables/use_sort';
import { preferences_parse } from '../../src/composables/use_preferences';
import { table_format, text_resolve, value_format } from '../../src/services/format';
import { fuzz_runs, fuzz_timeout } from '../support/fuzz';

const JSON_VALUE = fc.jsonValue({ maxDepth: 3 });

const SORTABLE = fc.oneof(
    fc.integer(),
    fc.double(),
    fc.constant(NaN),
    fc.constant(Infinity),
    fc.constant(-Infinity),
    fc.string({ maxLength: 6 }),
    fc.boolean(),
    fc.constant(null),
    fc.constant(undefined),
);

const FORMATS = fc.constantFrom(undefined, 'json' as const, 'table' as const, 'text' as const);

function row_compare(a: { value: unknown }, b: { value: unknown }): number {
    return compare_sort_values(a.value, b.value);
}

function row_value(row: { value: unknown }): unknown {
    return row.value;
}

function row_has_keys(row: unknown): boolean {
    if (row === null) return false;
    if (typeof row !== 'object') return false;
    return Object.keys(row).length > 0;
}

function sign(value: number): number {
    if (value < 0) return -1;
    if (value > 0) return 1;
    return 0;
}

describe('format under arbitrary input', function() {
    it('text_resolve answers text for any JSON value in any format', function() {
        fc.assert(
            fc.property(JSON_VALUE, FORMATS, function(value, format) {
                const text = text_resolve(value as object, format);

                expect(typeof text).toBe('string');
            }),
            { numRuns: fuzz_runs() },
        );
    }, fuzz_timeout());

    it('table_format answers text and one line per row for any array', function() {
        fc.assert(
            fc.property(fc.array(JSON_VALUE, { maxLength: 6 }), function(rows) {
                const text = table_format(rows);
                const has_object = rows.some(row_has_keys);

                expect(typeof text).toBe('string');

                if (has_object) {
                    expect(text.split('\n').length).toBe(rows.length + 2);
                }
            }),
            { numRuns: fuzz_runs() },
        );
    }, fuzz_timeout());

    it('value_format never throws on JSON values', function() {
        fc.assert(
            fc.property(JSON_VALUE, fc.integer({ max: 8, min: 0 }), function(value, indent) {
                expect(typeof value_format(value, indent)).toBe('string');
            }),
            { numRuns: fuzz_runs() },
        );
    }, fuzz_timeout());
});

describe('compare_sort_values under arbitrary input', function() {
    it('is reflexive and antisymmetric', function() {
        fc.assert(
            fc.property(SORTABLE, SORTABLE, function(a, b) {
                expect(compare_sort_values(a, a)).toBe(0);
                expect(sign(compare_sort_values(a, b)) + sign(compare_sort_values(b, a))).toBe(0);
            }),
            { numRuns: fuzz_runs() },
        );
    }, fuzz_timeout());

    it('is transitive', function() {
        fc.assert(
            fc.property(SORTABLE, SORTABLE, SORTABLE, function(a, b, c) {
                if (compare_sort_values(a, b) > 0) return;
                if (compare_sort_values(b, c) > 0) return;

                expect(compare_sort_values(a, c)).toBeLessThanOrEqual(0);
            }),
            { numRuns: fuzz_runs() * 5 },
        );
    }, fuzz_timeout());

    it(
        'sorts into non-decreasing order that agrees from any starting order up to ties',
        function() {
            fc.assert(
                fc.property(fc.array(SORTABLE, { maxLength: 12 }), function(values) {
                    const rows = values.map(function(value) { return { value: value }; });
                    const forward = rows.slice().sort(row_compare).map(row_value);
                    const backward = rows.slice().reverse().sort(row_compare).map(row_value);

                    for (let index = 1; index < forward.length; index++) {
                        const order = compare_sort_values(forward[index - 1], forward[index]);

                        expect(order).toBeLessThanOrEqual(0);
                    }

                    forward.forEach(function(value, index) {
                        expect(compare_sort_values(value, backward[index])).toBe(0);
                    });
                }),
                { numRuns: fuzz_runs() },
            );
        },
        fuzz_timeout(),
    );
});

describe('preferences_parse under arbitrary input', function() {
    const HOSTILE = fc.oneof(
        fc.string(),
        JSON_VALUE.map(function(value) { return JSON.stringify(value); }),
        fc.record({
            active_panel: JSON_VALUE,
            disabled: JSON_VALUE,
            launch: JSON_VALUE,
            order: JSON_VALUE,
            side: JSON_VALUE,
            state: JSON_VALUE,
        }, { requiredKeys: [] }).map(function(value) { return JSON.stringify(value); }),
    );

    it('answers null or a record whose every field is valid', function() {
        fc.assert(
            fc.property(HOSTILE, function(raw) {
                const parsed = preferences_parse(raw);

                if (parsed === null) return;

                expect(['left', 'right']).toContain(parsed.side);
                expect(['collapsed', 'strip', 'panel']).toContain(parsed.state);
                expect(typeof parsed.launch).toBe('string');

                if (parsed.active_panel !== null) {
                    expect(typeof parsed.active_panel).toBe('string');
                }

                for (const id of parsed.order) {
                    expect(typeof id).toBe('string');
                }

                expect(new Set(parsed.order).size).toBe(parsed.order.length);
                expect(parsed.order.length).toBeLessThanOrEqual(64);

                for (const value of Object.values(parsed.disabled)) {
                    expect(typeof value).toBe('boolean');
                }
            }),
            { numRuns: fuzz_runs() * 5 },
        );
    }, fuzz_timeout());
});
