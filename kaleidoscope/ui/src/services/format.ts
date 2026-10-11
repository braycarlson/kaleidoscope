import type { CopyFormat, CopyValue } from '../types';

const JSON_INDENT_MAX = 10;

export function text_resolve(value: CopyValue | null | undefined, format?: CopyFormat): string {
    if (typeof value === 'string') return value;
    if (value === null) return '';
    if (value === undefined) return '';

    const data = value as Record<string, unknown> | unknown[];

    if (format === 'table') return table_format(data);
    if (format === 'json') return JSON.stringify(data, null, 2);
    return plain_text_format(data);
}

function is_file_path(key: string): boolean {
    return /^[A-Za-z]:[\\/]/.test(key)
        || key.startsWith('/')
        || /\.(py|js|ts|vue|html|css|json|yaml|yml|toml|cfg|ini|txt|md|rst|sh|sql)$/i.test(key);
}

function is_multiline(value: unknown): value is string {
    return typeof value === 'string' && value.includes('\n');
}

export function value_format(value: unknown, indent = 0): string {
    if (!Number.isInteger(indent)) throw new RangeError('an indent must be an integer: ' + indent);
    if (indent < 0) throw new RangeError('an indent must not be negative: ' + indent);

    if (indent > JSON_INDENT_MAX) {
        throw new RangeError('an indent must be at most ' + JSON_INDENT_MAX + ': ' + indent);
    }

    if (value === null) return 'None';
    if (value === undefined) return 'None';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'object') return JSON.stringify(value, null, indent || undefined);
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    return typeof value;
}

function plain_text_format(value: Record<string, unknown> | unknown[]): string {
    if (Array.isArray(value)) {
        return value.map(function(item) {
            if (object_is(item)) {
                return Object.entries(item)
                    .map(function(pair) { return pair[0] + ': ' + value_format(pair[1]); })
                    .join(', ');
            }

            return value_format(item);
        }).join('\n');
    }

    const lines: string[] = [];

    for (const key of Object.keys(value)) {
        const val = value[key];

        if (is_file_path(key)) {
            lines.push(key);
            continue;
        }

        if (is_multiline(val)) {
            lines.push(key + ':');
            lines.push(val);
            lines.push('');
            continue;
        }

        lines.push(key + ': ' + value_format(val));
    }

    return lines.join('\n');
}

function object_is(value: unknown): value is Record<string, unknown> {
    if (value === null) return false;
    return typeof value === 'object';
}

function row_of(item: unknown): Record<string, unknown> {
    if (object_is(item)) return item;
    return {};
}

function cell_format(value: unknown): string {
    if (value === null) return '';
    if (value === undefined) return '';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'object') return JSON.stringify(value);
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    return typeof value;
}

export function table_format(value: Record<string, unknown> | unknown[]): string {
    const items: unknown[] = Array.isArray(value) ? value : [value];

    if (items.length === 0) return '';

    const columns: string[] = [];
    const column_set = new Set<string>();

    for (const item of items) {
        if (!object_is(item)) continue;

        for (const key of Object.keys(item)) {
            if (column_set.has(key)) continue;

            column_set.add(key);
            columns.push(key);
        }
    }

    if (columns.length === 0) return plain_text_format(value);

    const widths: number[] = columns.map(function(column) { return column.length; });

    const formatted_rows: string[][] = items.map(function(item) {
        const row = row_of(item);

        return columns.map(function(column, column_index) {
            const text = cell_format(row[column]);

            if (text.length > (widths[column_index] ?? 0)) {
                widths[column_index] = text.length;
            }

            return text;
        });
    });

    const header = columns.map(function(column, index) {
        return column.padEnd(widths[index] ?? 0);
    }).join('  ');

    const separator = widths.map(function(width) {
        return '-'.repeat(width);
    }).join('  ');

    if (header.length !== separator.length) {
        const mismatch = header.length + ' != ' + separator.length;
        throw new Error('a table header must match the width of its separator: ' + mismatch);
    }

    const body = formatted_rows.map(function(row) {
        return row.map(function(cell, index) {
            return cell.padEnd(widths[index] ?? 0);
        }).join('  ');
    }).join('\n');

    return header + '\n' + separator + '\n' + body;
}
