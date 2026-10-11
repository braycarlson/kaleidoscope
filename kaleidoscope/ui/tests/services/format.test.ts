import { describe, expect, it, vi } from 'vitest';
import { table_format, text_resolve, value_format } from '../../src/services/format';

describe('value_format', function() {
    it('spells Python literals for null, undefined, and booleans', function() {
        expect(value_format(null)).toBe('None');
        expect(value_format(undefined)).toBe('None');
        expect(value_format(true)).toBe('True');
        expect(value_format(false)).toBe('False');
    });

    it('serializes objects as JSON and everything else as text', function() {
        expect(value_format({ a: 1 })).toBe('{"a":1}');
        expect(value_format({ a: 1 }, 2)).toBe('{\n  "a": 1\n}');
        expect(value_format(3)).toBe('3');
        expect(value_format('text')).toBe('text');
    });
});

describe('text_resolve', function() {
    it('returns a string unchanged', function() {
        expect(text_resolve('plain', 'table')).toBe('plain');
    });

    it('formats an object as JSON when asked', function() {
        expect(text_resolve({ b: [1, 2] }, 'json')).toBe('{\n  "b": [\n    1,\n    2\n  ]\n}');
    });

    it('formats an object as key and value lines by default', function() {
        expect(text_resolve({ method: 'GET', status: 200 })).toBe('method: GET\nstatus: 200');
    });

    it('keeps a file path key on its own line', function() {
        expect(text_resolve({ '/app/views.py': 1, 'name': 'x' })).toBe('/app/views.py\nname: x');
    });

    it('sets a multiline value apart under its key', function() {
        expect(text_resolve({ sql: 'SELECT 1\nFROM t' })).toBe('sql:\nSELECT 1\nFROM t\n');
    });

    it('formats an array of objects as one line per object', function() {
        expect(text_resolve([{ a: 1, b: null }, 'x'])).toBe('a: 1, b: None\nx');
    });

    it('answers an empty string for null instead of throwing', function() {
        expect(text_resolve(null)).toBe('');
        expect(text_resolve(null, 'table')).toBe('');
        expect(text_resolve(null, 'json')).toBe('');
    });
});

describe('table_format', function() {
    it('aligns columns under a header and a separator', function() {
        const text = table_format([{ name: 'alpha', count: 1 }, { name: 'b', count: 22 }]);

        expect(text).toBe(
            'name   count\n'
            + '-----  -----\n'
            + 'alpha  1    \n'
            + 'b      22   ',
        );
    });

    it('unions the columns of rows with different keys', function() {
        const text = table_format([{ a: 1 }, { b: true }]);

        expect(text.split('\n')[0]).toBe('a  b   ');
        expect(text.split('\n')[3]).toBe('   True');
    });

    it('renders a single object as a one-row table', function() {
        expect(table_format({ key: 'value' })).toBe('key  \n-----\nvalue');
    });

    it('answers an empty string for an empty array', function() {
        expect(table_format([])).toBe('');
    });

    it('falls back to plain text when no row is an object', function() {
        expect(table_format([1, 'two'])).toBe('1\ntwo');
    });

    it('keeps going past null and primitive rows mixed with objects', function() {
        const text = table_format([null, { a: 1 }, 7, undefined]);

        expect(text.split('\n')).toEqual(['a', '-', ' ', '1', ' ', ' ']);
    });
});

describe('format outside JSON', function() {
    it('names values JSON cannot carry by their type', function() {
        expect(text_resolve(undefined)).toBe('');
        expect(value_format(BigInt(7))).toBe('bigint');
        expect(table_format([{ size: BigInt(7) }])).toBe('size  \n------\nbigint');
    });
});

describe('format contracts', function() {
    it.each([1.5, -1, 11, Number.NaN])('refuses an indent JSON cannot honor: %s', function(indent) {
        expect(function() { return value_format({ a: 1 }, indent); }).toThrow(RangeError);
    });

    it('refuses to return a header that does not span its separator', function() {
        function format_misaligned(): string {
            return table_format([{ count: 1, name: 'alpha' }]);
        }

        vi.spyOn(String.prototype, 'padEnd').mockImplementation(function(this: string) {
            return this;
        });

        expect(format_misaligned).toThrow('must match the width of its separator: 11 != 12');
    });
});

