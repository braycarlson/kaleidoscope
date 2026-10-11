import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import ProfilingPanel from '../../../src/components/panels/ProfilingPanel.vue';

const PROFILE = Object.freeze({
    duration_ms: 42,
    html: '<html>profile</html>',
    text: '42ms total',
});

function panel_mount(data: Record<string, unknown>): VueWrapper {
    return mount(ProfilingPanel, { props: { data: data } }) as VueWrapper;
}

function loading_shown(wrapper: VueWrapper): boolean {
    return wrapper.text().includes('Loading profile...');
}

beforeEach(function() {
    vi.useFakeTimers();
});

afterEach(function() {
    vi.useRealTimers();
});

describe('ProfilingPanel states', function() {
    it('shows the error the server reported instead of a profile', function() {
        const wrapper = panel_mount({ error: 'profiler unavailable' });

        expect(wrapper.text()).toBe('profiler unavailable');
    });

    it('explains how to capture a profile when there is none', function() {
        const wrapper = panel_mount({});

        expect(wrapper.text()).toContain('Duration0 ms');
        expect(wrapper.text()).toContain('No profile captured yet');
        expect(wrapper.find('iframe').exists()).toBe(false);
    });
});

describe('ProfilingPanel loading', function() {
    it('hides the loading cover once the profile and its fonts are ready', async function() {
        const wrapper = panel_mount({ ...PROFILE });
        const iframe = wrapper.get('iframe');
        const document_framed = { fonts: { ready: Promise.resolve() } };

        Object.defineProperty(iframe.element, 'contentDocument', {
            configurable: true,
            value: document_framed,
        });

        expect(loading_shown(wrapper)).toBe(true);

        await iframe.trigger('load');
        await vi.advanceTimersByTimeAsync(300);

        expect(loading_shown(wrapper)).toBe(false);
    });

    it('hides the loading cover after a delay when the profile cannot be read', async function() {
        const wrapper = panel_mount({ ...PROFILE });
        const iframe = wrapper.get('iframe');
        const descriptor = { configurable: true, value: null };

        Object.defineProperty(iframe.element, 'contentDocument', descriptor);

        await iframe.trigger('load');
        await vi.advanceTimersByTimeAsync(499);

        expect(loading_shown(wrapper)).toBe(true);

        await vi.advanceTimersByTimeAsync(1);

        expect(loading_shown(wrapper)).toBe(false);
    });

    it('treats a cross-origin profile like one it cannot read', async function() {
        const wrapper = panel_mount({ ...PROFILE });
        const iframe = wrapper.get('iframe');

        function refused(): Document {
            throw new DOMException('Blocked a frame', 'SecurityError');
        }

        const descriptor = { configurable: true, get: refused };

        Object.defineProperty(iframe.element, 'contentDocument', descriptor);

        await iframe.trigger('load');
        await vi.advanceTimersByTimeAsync(500);

        expect(loading_shown(wrapper)).toBe(false);
    });

});

describe('ProfilingPanel changes', function() {
    it('covers a new profile again and folds the profile away on request', async function() {
        const wrapper = panel_mount({ ...PROFILE });

        await wrapper.get('iframe').trigger('load');
        await vi.advanceTimersByTimeAsync(300);
        await wrapper.setProps({ data: { ...PROFILE, html: '<html>newer</html>' } });

        expect(loading_shown(wrapper)).toBe(true);

        const toggle = wrapper.findAll('div.cursor-pointer').find(function(element) {
            return element.text() === 'Profile';
        });

        await toggle?.trigger('click');

        expect(wrapper.get('div.relative').attributes('style')).toContain('display: none');
    });
});
