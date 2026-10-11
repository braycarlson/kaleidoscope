import { describe, expect, it } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import type { Component } from 'vue';
import RequestPanel from '../../../src/components/panels/RequestPanel.vue';
import { vue_reports } from '../../support/setup';

function session_build(overrides: Record<string, unknown> = {}) {
    return {
        accessed: true,
        backend: 'django.contrib.sessions.backends.db.SessionStore',
        expire_at_browser_close: false,
        expiry_age: 1_209_600,
        items: { cart: [1, 2] },
        modified: false,
        ...overrides,
    };
}

function user_build() {
    return {
        active: true,
        authenticated: true,
        id: '4',
        name: 'reader',
        staff: false,
        superuser: false,
    };
}

function check_build(overrides: Record<string, unknown> = {}) {
    return {
        count: 1,
        kind: 'permission',
        name: 'app.view_book',
        result: false,
        superuser: false,
        target: '',
        ...overrides,
    };
}

function data_build(overrides: Record<string, unknown> = {}) {
    return {
        headers: { Host: 'testserver' },
        method: 'GET',
        path: '/books/',
        permissions: [],
        session: null,
        status_code: 200,
        user: null,
        ...overrides,
    };
}

function panel_mount(data: Record<string, unknown>): VueWrapper {
    return mount(RequestPanel as Component, { props: { data: data } }) as VueWrapper;
}

function sections_of(wrapper: VueWrapper): string[] {
    return wrapper.findAllComponents({ name: 'CollapsibleSection' }).map(function(section) {
        return String(section.props('title'));
    });
}

function rows_of(wrapper: VueWrapper, selector: string): string[] {
    return wrapper.findAll(selector).map(function(row) {
        return row.findAll('td').map(function(cell) { return cell.text(); }).join('|');
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

describe('RequestPanel user, checks, and session', function() {
    it('shows the user the request was for', function() {
        const wrapper = panel_mount(data_build({ user: user_build() }));
        const text = wrapper.text();

        expect(sections_of(wrapper)).toContain('User');
        expect(text).toContain('Namereader');
        expect(text).toContain('ID4');
        expect(text).toContain('AuthenticatedTrue');
        expect(text).toContain('SuperuserFalse');
    });

    it('lists each permission check with its object, its result, and its count', function() {
        const permissions = [
            check_build({ count: 2 }),
            check_build({ kind: 'module', name: 'app', result: true, superuser: true }),
            check_build({ name: 'app.change_book', target: 'Book 4' }),
        ];

        const wrapper = panel_mount(data_build({ permissions: permissions }));

        expect(rows_of(wrapper, '[data-ks="permission-check"]')).toEqual([
            'app.view_book||Denied|2',
            'app (module)||Granted as superuser|1',
            'app.change_book|Book 4|Denied|1',
        ]);
    });

    it('shows the session with its state and its items', function() {
        const wrapper = panel_mount(data_build({ session: session_build() }));
        const text = wrapper.text();

        expect(text).toContain('Backenddjango.contrib.sessions.backends.db.SessionStore');
        expect(text).toContain('AccessedTrue');
        expect(text).toContain('ModifiedFalse');
        expect(text).toContain('Expiresin 14 d');
        expect(rows_of(wrapper, '[data-ks="session-item"]')).toEqual(['cart|[1,2]']);
    });

    it.each([
        [{ expire_at_browser_close: true }, 'Expireswhen the browser closes'],
        [{ expiry_age: 30 }, 'Expiresin 30 s'],
        [{ expiry_age: 120 }, 'Expiresin 2 min'],
        [{ expiry_age: 7_200 }, 'Expiresin 2 h'],
    ])('words the expiry of a session that ends %j', function(overrides, expected) {
        const wrapper = panel_mount(data_build({ session: session_build(overrides) }));

        expect(wrapper.text()).toContain(expected);
    });

    it('leaves out the user, the checks, and the session a request did not carry', function() {
        const sections = sections_of(panel_mount(data_build()));

        expect(sections).not.toContain('User');
        expect(sections).not.toContain('Permission Checks');
        expect(sections).not.toContain('Session');
    });
});

describe('RequestPanel user, checks, and session checks', function() {
    it.each([
        [
            data_build({ permissions: [check_build({ count: NaN })] }),
            'RangeError: a permission check count must be finite: NaN',
        ],
        [
            data_build({ session: session_build({ expiry_age: NaN }) }),
            'RangeError: a session expiry must be finite: NaN',
        ],
        [
            data_build({ session: session_build({ items: ['cart'] }) }),
            'TypeError: request data must be a record, not a list',
        ],
    ])('refuses %j', function(data, message) {
        expect(reported_by(data)).toContain(message);
    });
});
