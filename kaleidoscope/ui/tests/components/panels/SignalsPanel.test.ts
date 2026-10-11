import { describe, expect, it } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import SignalsPanel from '../../../src/components/panels/SignalsPanel.vue';
import { vue_reports } from '../../support/setup';

const SITE = Object.freeze({
    file: '/app/views.py',
    function: 'shelve',
    line: 9,
    text: 'shelved.send(sender=Book)',
});

function send_build(overrides: Record<string, unknown> = {}) {
    return {
        count: 3,
        duration_ms: 12.5,
        errors: 1,
        module: 'app.signals.shelved',
        name: 'shelved',
        receivers: ['app.receivers.shelve'],
        sender: 'app.models.Book',
        site: { ...SITE },
        ...overrides,
    };
}

function data_build(sends: unknown[], overrides: Record<string, unknown> = {}) {
    return {
        count: 0,
        send_count: 3,
        send_time: 12.5,
        sends: sends,
        signals: [],
        total_receivers: 0,
        ...overrides,
    };
}

function panel_mount(data: Record<string, unknown>): VueWrapper {
    return mount(SignalsPanel as Component, { props: { data: data } }) as VueWrapper;
}

function sections_of(wrapper: VueWrapper): string[] {
    return wrapper.findAllComponents({ name: 'CollapsibleSection' }).map(function(section) {
        return String(section.props('title'));
    });
}

function reported_by(data: Record<string, unknown>): string {
    let thrown = '';

    try {
        panel_mount(data).unmount();
    } catch (error: unknown) {
        thrown = String(error);
    }

    return [thrown, ...vue_reports.splice(0)].join('\n');
}

describe('SignalsPanel sends', function() {
    it('shows each signal the page sent with its sender, count, time, and errors', function() {
        const wrapper = panel_mount(data_build([send_build()]));
        const cells = wrapper.findAll('tbody tr td').map(function(cell) { return cell.text(); });

        expect(wrapper.text()).toContain('Sends3');
        expect(wrapper.text()).toContain('Send Time12.5 ms');
        expect(sections_of(wrapper)).toEqual(['Sent', 'Signals']);
        expect(cells).toEqual(['shelved', 'app.models.Book', '3', '12.50 ms', '1']);
    });

    it('expands a send into where it was sent and the receivers that ran', async function() {
        const wrapper = panel_mount(data_build([send_build()]));

        await wrapper.get('tbody tr').trigger('click');

        const site = wrapper.get('[data-ks="send-site"]').text();

        expect(site).toContain('/app/views.py:9');
        expect(site).toContain('shelved.send(sender=Book)');
        expect(wrapper.text()).toContain('app.receivers.shelve');
    });

    it('says no receiver ran for a send with no receivers and no site', async function() {
        const send = send_build({ errors: 0, receivers: [], site: null });
        const wrapper = panel_mount(data_build([send]));

        await wrapper.get('tbody tr').trigger('click');

        expect(wrapper.find('[data-ks="send-site"]').exists()).toBe(false);
        expect(wrapper.text()).toContain('No receivers ran');
    });

    it('shows a site that names no line text by its place alone', async function() {
        const send = send_build({ site: { ...SITE, text: '' } });
        const wrapper = panel_mount(data_build([send]));

        await wrapper.get('tbody tr').trigger('click');

        expect(wrapper.get('[data-ks="send-site"]').text()).toBe('Sent from/app/views.py:9');
    });

});

describe('SignalsPanel send filters and marks', function() {
    it('filters the sends by signal or sender', async function() {
        const other = send_build({
            module: 'app.signals.lent',
            name: 'lent',
            sender: 'app.models.Loan',
        });

        const wrapper = panel_mount(data_build([send_build(), other]));
        const input = wrapper.findAll('input').at(0);

        if (input === undefined) throw new Error('no send filter');

        await input.setValue('loan');

        const names = wrapper.findAll('tbody tr td:first-child').map(function(cell) {
            return cell.text();
        });

        expect(names).toEqual(['lent']);
    });

    it('marks a slow send and leaves a clean one unmarked', function() {
        const slow = send_build({ duration_ms: 40, errors: 0 });
        const wrapper = panel_mount(data_build([slow]));

        expect(wrapper.find('span.text-orange-500').text()).toBe('40.00 ms');
        expect(wrapper.find('span.text-red-500').exists()).toBe(false);
    });

    it('leaves the sent section out when the page sent nothing', function() {
        const wrapper = panel_mount(data_build([], { send_count: 0, send_time: 0 }));

        expect(sections_of(wrapper)).toEqual(['Signals']);
    });
});

describe('SignalsPanel send checks', function() {
    it.each([
        [
            data_build([], { send_time: NaN }),
            'RangeError: a send time must be a finite number: NaN',
        ],
        [
            data_build([send_build({ count: NaN })]),
            'RangeError: a send count must be finite: NaN',
        ],
        [
            data_build([send_build({ duration_ms: NaN })]),
            'RangeError: a send time must be finite: NaN',
        ],
        [
            data_build([send_build({ errors: '1' })]),
            'RangeError: a send error count must be finite: 1',
        ],
        [
            data_build([send_build({ name: 5 })]),
            'TypeError: a sent signal name must be text: 5',
        ],
    ])('refuses %j', function(data, message) {
        expect(reported_by(data)).toContain(message);
    });
});
