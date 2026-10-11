import { beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest';
import { defineComponent, h } from 'vue';
import { mount } from '@vue/test-utils';

const STORAGE_KEY = 'ks-theme';

function host_render() {
    return h('div');
}

async function theme_load() {
    vi.resetModules();

    const module = await import('../../src/composables/use_theme');

    return module.use_theme();
}

beforeEach(function() {
    localStorage.clear();
});

describe('use_theme', function() {
    it('starts dark without a stored choice', async function() {
        const { theme } = await theme_load();

        expect(theme.value).toBe('dark');
    });

    it('restores a stored dark theme', async function() {
        localStorage.setItem(STORAGE_KEY, 'dark');

        const { theme } = await theme_load();

        expect(theme.value).toBe('dark');
    });

    it('restores a stored light theme and ignores anything else', async function() {
        localStorage.setItem(STORAGE_KEY, 'light');

        const light = await theme_load();

        expect(light.theme.value).toBe('light');

        localStorage.setItem(STORAGE_KEY, 'purple');

        const purple = await theme_load();

        expect(purple.theme.value).toBe('dark');
    });

    it('toggles between dark and light and remembers the choice', async function() {
        const { theme, toggle } = await theme_load();

        toggle();

        expect(theme.value).toBe('light');
        expect(localStorage.getItem(STORAGE_KEY)).toBe('light');

        toggle();

        expect(theme.value).toBe('dark');
        expect(localStorage.getItem(STORAGE_KEY)).toBe('dark');
    });

    it('works with storage that refuses every read and write', async function() {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function() {
            throw new Error('storage is denied');
        });

        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function() {
            throw new Error('storage is denied');
        });

        const { theme, toggle } = await theme_load();

        toggle();

        expect(theme.value).toBe('light');
    });
});

describe('use_mobile', function() {
    function width_set(width: number) {
        const descriptor = { configurable: true, value: width, writable: true };

        Object.defineProperty(window, 'innerWidth', descriptor);
    }

    it('follows the window width across the breakpoint', async function() {
        const { use_mobile } = await import('../../src/composables/use_mobile');
        let mobile: ReturnType<typeof use_mobile> | null = null;

        const Host = defineComponent({
            setup() {
                mobile = use_mobile();

                return host_render;
            },
        });

        width_set(1200);

        const wrapper = mount(Host);
        const state = mobile as unknown as ReturnType<typeof use_mobile>;
        let mounted = true;

        onTestFinished(function() {
            if (!mounted) return;

            wrapper.unmount();
        });

        expect(state.is_mobile.value).toBe(false);

        width_set(400);
        window.dispatchEvent(new Event('resize'));

        expect(state.is_mobile.value).toBe(true);

        wrapper.unmount();
        mounted = false;
        width_set(1200);
        window.dispatchEvent(new Event('resize'));

        expect(state.is_mobile.value).toBe(true);
    });
});
