import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import RowsMore from '../../src/components/RowsMore.vue';
import { vue_reports } from '../support/setup';

function props_of(columns: number, hidden: number) {
    return { columns: columns, hidden_count: hidden };
}

describe('RowsMore', function() {
    it('offers the hidden rows across every column', async function() {
        const wrapper = mount(RowsMore, { props: props_of(6, 50) });
        const button = wrapper.get('[data-ks="rows-more"]');

        expect(wrapper.get('td').attributes('colspan')).toBe('6');
        expect(button.text()).toBe('Show 50 more');

        await button.trigger('click');

        expect(wrapper.emitted('more')).toHaveLength(1);
    });

    it.each([
        [0, 5, RangeError, 'columns must be at least 1: 0'],
        [1.5, 5, TypeError, 'columns must be an integer: 1.5'],
        [2, 0, RangeError, 'hidden_count must be at least 1: 0'],
        [2, 2.5, TypeError, 'hidden_count must be an integer: 2.5'],
    ])('refuses %s columns with %s hidden rows', function(columns, hidden, error, message) {
        const props = props_of(columns, hidden);

        expect(function() { mount(RowsMore, { props: props }); }).toThrow(error);

        const reports = vue_reports.splice(0);

        expect(reports).toEqual(['error: ' + error.name + ': ' + message]);
    });
});
