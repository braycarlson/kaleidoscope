import { describe, expect, it, onTestFinished, vi } from 'vitest';
import { use_interceptors } from '../../src/composables/use_interceptors';
import { json_response } from '../support/fetch';

interface Stubs {
    fetch_calls: unknown[][];
    open_calls: unknown[][];
}

const open_real = XMLHttpRequest.prototype.open;
const send_real = XMLHttpRequest.prototype.send;

function prototypes_restore() {
    XMLHttpRequest.prototype.open = open_real;
    XMLHttpRequest.prototype.send = send_real;
}

function send_stub() {
    return undefined;
}

function stubs_install(fetch_failing: boolean): Stubs {
    const fetch_calls: unknown[][] = [];
    const open_calls: unknown[][] = [];

    function fetch_stub(...args: unknown[]): Promise<Response> {
        fetch_calls.push(args);

        if (fetch_failing) {
            return Promise.reject(new TypeError('Failed to fetch'));
        }

        return Promise.resolve(json_response(200, {}));
    }

    function open_stub(...args: unknown[]) {
        open_calls.push(args);
    }

    XMLHttpRequest.prototype.open = open_stub;
    XMLHttpRequest.prototype.send = send_stub;
    vi.stubGlobal('fetch', fetch_stub);
    onTestFinished(prototypes_restore);

    return { fetch_calls, open_calls };
}

function interceptors_install(activity: () => void, fetch_failing: boolean): Stubs {
    const stubs = stubs_install(fetch_failing);
    const cleanup = use_interceptors(activity);

    onTestFinished(cleanup);

    return stubs;
}

function request_sent(url: string): XMLHttpRequest {
    const request = new XMLHttpRequest();

    request.open('GET', url);
    request.send();

    return request;
}

describe('use_interceptors over XHR', function() {
    it('reports activity once each XHR of the page finishes', function() {
        const activity = vi.fn();

        interceptors_install(activity, false);

        const request = request_sent('/api/books/');

        expect(activity).not.toHaveBeenCalled();

        request.dispatchEvent(new Event('loadend'));

        expect(activity).toHaveBeenCalledTimes(1);
    });

    it('reports a reused XHR once per request rather than once per earlier send', function() {
        const activity = vi.fn();

        interceptors_install(activity, false);

        const request = new XMLHttpRequest();

        for (let index = 0; index < 3; index++) {
            request.open('GET', '/api/books/');
            request.send();
            request.dispatchEvent(new Event('loadend'));
        }

        expect(activity).toHaveBeenCalledTimes(3);
    });

    it.each([
        '/__kaleidoscope__/panels/',
        'http://localhost:3000/__kaleidoscope__/panels/queries/data/',
        '//localhost:3000/__kaleidoscope__/static/kaleidoscope.js',
    ])('ignores the toolbar requesting itself by XHR: %s', function(url) {
        const activity = vi.fn();

        interceptors_install(activity, false);
        request_sent(url).dispatchEvent(new Event('loadend'));

        expect(activity).not.toHaveBeenCalled();
    });

    it('forwards every argument of open untouched', function() {
        const { open_calls } = interceptors_install(vi.fn(), false);
        const request = new XMLHttpRequest();

        request.open('POST', '/api/', false);
        request.open('GET', '/api/');

        expect(open_calls).toEqual([['POST', '/api/', false], ['GET', '/api/']]);
    });
});

describe('use_interceptors over fetch', function() {
    it('reports activity once a fetch of the page resolves', async function() {
        const activity = vi.fn();

        interceptors_install(activity, false);

        const response = await window.fetch('/api/books/');

        expect(response.status).toBe(200);
        expect(activity).toHaveBeenCalledTimes(1);
    });

    it.each([
        ['a relative toolbar URL', '/__kaleidoscope__/panels/'],
        ['an absolute toolbar URL', 'http://localhost:3000/__kaleidoscope__/panels/'],
        ['a toolbar URL object', new URL('http://localhost:3000/__kaleidoscope__/panels/')],
        ['a toolbar request object', new Request('http://localhost:3000/__kaleidoscope__/panels/')],
    ])('ignores the toolbar requesting itself by fetch with %s', async function(_name, input) {
        const activity = vi.fn();

        interceptors_install(activity, false);
        await window.fetch(input);

        expect(activity).not.toHaveBeenCalled();
    });

    it('lets a failed fetch reject without reporting activity', async function() {
        const activity = vi.fn();

        interceptors_install(activity, true);

        await expect(window.fetch('/api/')).rejects.toThrow('Failed to fetch');
        expect(activity).not.toHaveBeenCalled();
    });

    it('calls the real fetch with the window as its receiver', async function() {
        const { fetch_calls } = interceptors_install(vi.fn(), false);
        const detached = window.fetch;

        await detached.call({}, '/api/');

        expect(fetch_calls).toEqual([['/api/', undefined]]);
    });

    it('restores fetch and XHR when cleaned up', function() {
        stubs_install(false);

        const fetch_before = window.fetch;
        const open_before = XMLHttpRequest.prototype.open;
        const restore = use_interceptors(vi.fn());

        expect(window.fetch).not.toBe(fetch_before);

        restore();

        expect(window.fetch).toBe(fetch_before);
        expect(XMLHttpRequest.prototype.open).toBe(open_before);
    });
});

describe('use_interceptors over unparseable addresses', function() {
    it('reads an address it cannot parse as a page request', async function() {
        const activity = vi.fn();

        interceptors_install(activity, false);

        await window.fetch('http://[broken');

        expect(activity).toHaveBeenCalledTimes(1);
    });
});
