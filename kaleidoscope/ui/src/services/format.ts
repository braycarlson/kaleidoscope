import type { CopyFormat, CopyValue } from '../types';

export function text_resolve(value: CopyValue, format?: CopyFormat): string {
    if (typeof value === 'string') return value;

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

function is_multiline(value: unknown): boolean {
    return typeof value === 'string' && value.includes('\n');
}

export function value_format(value: unknown, indent: number = 0): string {
    if (value === null || value === undefined) return 'None';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'object') return JSON.stringify(value, null, indent || undefined);
    return String(value);
}

function plain_text_format(value: Record<string, unknown> | unknown[]): string {
    if (Array.isArray(value)) {
        return value.map(function(item) {
            if (typeof item === 'object' && item !== null) {
                return Object.entries(item as Record<string, unknown>)
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
            lines.push(String(val));
            lines.push('');
            continue;
        }

        lines.push(key + ': ' + value_format(val));
    }

    return lines.join('\n');
}

function cell_format(value: unknown): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

export function table_format(value: Record<string, unknown> | unknown[]): string {
    const items: Record<string, unknown>[] = Array.isArray(value)
        ? value as Record<string, unknown>[]
        : [value];

    if (!items.length) return '';

    const columns: string[] = [];
    const column_set = new Set<string>();

    for (let index = 0; index < items.length; index++) {
        if (items[index] && typeof items[index] === 'object') {
            for (const key of Object.keys(items[index])) {
                if (!column_set.has(key)) {
                    column_set.add(key);
                    columns.push(key);
                }
            }
        }
    }

    if (!columns.length) return plain_text_format(value);

    const widths: number[] = columns.map(function(column) { return column.length; });

    const formatted_rows: string[][] = items.map(function(item) {
        return columns.map(function(column, column_index) {
            const text = cell_format(item[column]);
            if (text.length > widths[column_index]) widths[column_index] = text.length;
            return text;
        });
    });

    const header = columns.map(function(column, index) {
        return column.padEnd(widths[index]);
    }).join('  ');

    const separator = widths.map(function(width) {
        return '-'.repeat(width);
    }).join('  ');

    const body = formatted_rows.map(function(row) {
        return row.map(function(cell, index) {
            return cell.padEnd(widths[index]);
        }).join('  ');
    }).join('\n');

    return header + '\n' + separator + '\n' + body;
}
