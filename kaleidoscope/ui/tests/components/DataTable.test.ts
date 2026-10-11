import { describe, expect, it } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import DataTable from '../../src/components/DataTable.vue';
import type { TableColumn } from '../../src/services/table';
import { vue_reports } from '../support/setup';

interface Row {
    name: string;
}

interface DataTableInternals {
    is_expanded: (index: number) => boolean;
    on_row_click: (row: Row, index: number) => void;
}

const COLUMN_NAME: TableColumn<Row> = Object.freeze({ accessorKey: 'name', header: 'Name' });
const COLUMNS: readonly TableColumn<Row>[] = Object.freeze([COLUMN_NAME]);
const ROWS: readonly Row[] = Object.freeze([{ name: 'alpha' }, { name: 'beta' }]);

function table_mount(columns: readonly TableColumn<Row>[]): VueWrapper {
    const props = { columns: columns, data: ROWS, expandable: true };

    return mount(DataTable as Component, { props: props }) as VueWrapper;
}

describe('DataTable rows', function() {
    it('expands a clicked row and reports which row it was', async function() {
        const wrapper = table_mount(COLUMNS);

        await wrapper.get('tbody tr').trigger('click');

        expect(wrapper.emitted('row-click')).toEqual([[ROWS[0], 0]]);
        expect((wrapper.vm as unknown as DataTableInternals).is_expanded(0)).toBe(true);
    });

    it('adopts a default sorting that arrives after it mounts', async function() {
        const wrapper = table_mount(COLUMNS);

        await wrapper.setProps({ sorting_default: [{ desc: true, id: 'name' }] });

        const names = wrapper.findAll('tbody tr td').map(function(cell) { return cell.text(); });

        expect(names).toEqual(['beta', 'alpha']);
    });

    it('refuses a row index that is not a row of its data', function() {
        const table = table_mount(COLUMNS).vm as unknown as DataTableInternals;
        const row = { name: 'alpha' };
        const message = 'a row index must be below 2: 2';

        expect(function() { table.is_expanded(0.5); }).toThrow(TypeError);
        expect(function() { table.is_expanded(-1); }).toThrow(RangeError);
        expect(function() { table.on_row_click(row, 2); }).toThrow(message);
    });

    it('refuses a table without columns', function() {
        const report = 'error: RangeError: a data table needs at least one column';

        expect(function() { table_mount([]); }).toThrow(RangeError);

        const reports = vue_reports.splice(0);

        expect(reports).toEqual([report]);
    });
});
