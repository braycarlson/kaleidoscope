import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { fetch_fake_create } from './support/fetch';

async function main_load(): Promise<void> {
    const fake = fetch_fake_create();

    vi.stubGlobal('fetch', fake.fetch);
    vi.resetModules();

    await import('../src/main');
}

afterEach(function() {
    document.body.innerHTML = '';
    localStorage.clear();
});

describe('main', function() {
    it('refuses to start without its mount point', async function() {
        await expect(main_load()).rejects.toThrow('#ks-app not found');
    });

    it('mounts the toolbar into an open shadow root once its stylesheet settles', async function() {
        const host = document.createElement('div');

        host.id = 'ks-app';
        document.body.appendChild(host);

        await main_load();

        const shadow = host.shadowRoot;
        const link = shadow?.querySelector('link');

        expect(link?.getAttribute('href')).toBe('/__kaleidoscope__/static/kaleidoscope.css');
        expect(shadow?.querySelector('[data-ks="tab"]')).toBeNull();

        link?.dispatchEvent(new Event('load'));
        link?.dispatchEvent(new Event('error'));
        await flushPromises();

        expect(shadow?.querySelectorAll('[data-ks="tab"]')).toHaveLength(1);
    });

    it('reopens the strip saved under the launch the server stamped on its host', async function() {
        const host = document.createElement('div');
        const preferences = JSON.stringify({ launch: 'launch-1', state: 'strip' });

        host.id = 'ks-app';
        host.dataset['launch'] = 'launch-1';
        document.body.appendChild(host);
        localStorage.setItem('kaleidoscope_preferences', preferences);

        await main_load();

        const shadow = host.shadowRoot;

        shadow?.querySelector('link')?.dispatchEvent(new Event('load'));
        await flushPromises();

        expect(shadow?.querySelector('[data-ks="strip"]')).not.toBeNull();
        expect(shadow?.querySelector('[data-ks="tab"]')).toBeNull();
    });
});
