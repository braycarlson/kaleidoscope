import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import CopyButton from '../../src/components/CopyButton.vue';
import { COPY_FEEDBACK_MS } from '../../src/constants';
import { vue_reports } from '../support/setup';

function clipboard_set(clipboard: unknown) {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: clipboard });
}

function copy_refused(): never {
    throw new Error('unsupported');
}

function write_refused(): Promise<void> {
    return Promise.reject(new Error('denied'));
}

beforeEach(function() {
    vi.useFakeTimers();
});

afterEach(function() {
    vi.useRealTimers();
});

describe('CopyButton', function() {
    it('copies the formatted value and confirms for a moment', async function() {
        const written: string[] = [];

        function write_text(text: string): Promise<void> {
            written.push(text);

            return Promise.resolve();
        }

        clipboard_set({ writeText: write_text });

        const wrapper = mount(CopyButton, {
            props: { format: 'table', label: 'Copy', value: [{ a: 1 }] },
        });

        await wrapper.trigger('click');
        await flushPromises();

        expect(written).toEqual(['a\n-\n1']);
        expect(wrapper.text()).toBe('Copied');

        vi.advanceTimersByTime(COPY_FEEDBACK_MS);
        await flushPromises();

        expect(wrapper.text()).toBe('Copy');
    });
});

describe('CopyButton fallbacks', function() {
    it('falls back to a selection copy where the clipboard API is missing', async function() {
        clipboard_set(undefined);

        const execute = vi.fn().mockReturnValue(true);

        Object.defineProperty(document, 'execCommand', { configurable: true, value: execute });

        const wrapper = mount(CopyButton, { props: { label: 'Copy', value: 'plain text' } });

        await wrapper.trigger('click');
        await flushPromises();

        expect(execute).toHaveBeenCalledWith('copy');
        expect(wrapper.text()).toBe('Copied');
        expect(document.querySelectorAll('textarea').length).toBe(0);
    });

    it('falls back when the clipboard API refuses permission', async function() {
        clipboard_set({ writeText: write_refused });

        const execute = vi.fn().mockReturnValue(true);

        Object.defineProperty(document, 'execCommand', { configurable: true, value: execute });

        const wrapper = mount(CopyButton, { props: { label: 'Copy', value: 'x' } });

        await wrapper.trigger('click');
        await flushPromises();

        expect(execute).toHaveBeenCalledWith('copy');
        expect(wrapper.text()).toBe('Copied');
    });

    it('confirms nothing when every way to copy fails', async function() {
        clipboard_set(undefined);

        Object.defineProperty(document, 'execCommand', { configurable: true, value: copy_refused });

        const wrapper = mount(CopyButton, { props: { label: 'Copy', value: 'x' } });

        await wrapper.trigger('click');
        await flushPromises();

        expect(wrapper.text()).toBe('Copy');
    });
});

describe('CopyButton timing', function() {
    function write_accepted(): Promise<void> {
        return Promise.resolve();
    }

    function clipboard_accepting(): void {
        clipboard_set({ writeText: write_accepted });
    }

    it('keeps confirming for the full delay after a second copy', async function() {
        clipboard_accepting();

        const wrapper = mount(CopyButton, { props: { label: 'Copy', value: 'text' } });

        await wrapper.trigger('click');
        await flushPromises();
        vi.advanceTimersByTime(COPY_FEEDBACK_MS - 100);
        await wrapper.trigger('click');
        await flushPromises();
        vi.advanceTimersByTime(200);
        await flushPromises();

        expect(wrapper.text()).toBe('Copied');

        vi.advanceTimersByTime(COPY_FEEDBACK_MS);
        await flushPromises();

        expect(wrapper.text()).toBe('Copy');
    });

    it('cancels its confirmation timer when unmounted', async function() {
        clipboard_accepting();

        const wrapper = mount(CopyButton, { props: { label: 'Copy', value: 'text' } });

        await wrapper.trigger('click');
        await flushPromises();
        wrapper.unmount();

        expect(vi.getTimerCount()).toBe(0);
    });

    it('falls back when the clipboard API lacks a write method', async function() {
        clipboard_set({});

        const execute = vi.fn().mockReturnValue(true);

        Object.defineProperty(document, 'execCommand', { configurable: true, value: execute });

        const wrapper = mount(CopyButton, { props: { label: 'Copy', value: 'text' } });

        await wrapper.trigger('click');
        await flushPromises();

        expect(execute).toHaveBeenCalledWith('copy');
    });
});

describe('CopyButton icon', function() {
    it('draws its icon at the size it is given or at the default', function() {
        const sized = mount(CopyButton, { props: { size: 11, value: 'x' } });
        const plain = mount(CopyButton, { props: { value: 'x' } });

        expect(sized.get('svg').attributes('width')).toBe('11');
        expect(plain.get('svg').attributes('width')).toBe('13');
    });

    it('refuses an icon size that is not a positive finite number', function() {
        const empty = { size: 0, value: 'x' };
        const infinite = { size: Number.POSITIVE_INFINITY, value: 'x' };

        expect(function() { mount(CopyButton, { props: empty }); }).toThrow(RangeError);
        expect(function() { mount(CopyButton, { props: infinite }); }).toThrow(RangeError);

        const reports = vue_reports.splice(0);

        expect(reports).toEqual([
            'error: RangeError: an icon size must be positive: 0',
            'error: RangeError: an icon size must be finite: Infinity',
        ]);
    });
});
