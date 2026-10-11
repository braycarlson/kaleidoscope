import { describe, expect, it } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import KaleidoscopeStrip from '../../src/components/KaleidoscopeStrip.vue';
import KaleidoscopeTab from '../../src/components/KaleidoscopeTab.vue';
import type { PanelMeta } from '../../src/types';

interface StripInternals {
    on_drag_over: (index: number, event: DragEvent) => void;
    on_drag_start: (index: number, event: DragEvent) => void;
    on_drop: (index: number) => void;
}

const CONTROL_SELECTORS = Object.freeze([
    '[data-ks="theme"]',
    '[data-ks="strip-close"]',
    '[data-ks="swap"]',
    '[data-ks="collapse"]',
    '[data-ks-toggle]',
]);

function panels_built(): PanelMeta[] {
    return [
        { enabled: true, id: 'timer', isolate: false, summary: '', title: 'Timer' },
        { enabled: false, id: 'queries', isolate: false, summary: '', title: 'SQL Queries' },
    ];
}

describe('KaleidoscopeStrip', function() {
    it('exposes each toggle as a named switch with its state', function() {
        const props = { panels: panels_built(), panels_disabled: { queries: true } };
        const wrapper = mount(KaleidoscopeStrip, { props });
        const timer = wrapper.get('[data-ks-toggle="timer"]');
        const queries = wrapper.get('[data-ks-toggle="queries"]');

        expect(timer.element.tagName).toBe('BUTTON');
        expect(timer.attributes('role')).toBe('switch');
        expect(timer.attributes('aria-checked')).toBe('true');
        expect(timer.attributes('aria-label')).toBe('Enable Timer');
        expect(queries.attributes('aria-checked')).toBe('false');
    });

    it('renders every control as a button that never submits a form', function() {
        const wrapper = mount(KaleidoscopeStrip, { props: { panels: panels_built() } });
        const controls = wrapper.findAll(CONTROL_SELECTORS.join(', '));

        expect(controls.length).toBe(6);

        for (const control of controls) {
            expect(control.element.tagName).toBe('BUTTON');
            expect(control.attributes('type')).toBe('button');
        }
    });

    it('toggles a panel without selecting it', async function() {
        const wrapper = mount(KaleidoscopeStrip, { props: { panels: panels_built() } });

        await wrapper.get('[data-ks-toggle="timer"]').trigger('click');

        expect(wrapper.emitted('toggle')).toEqual([['timer']]);
        expect(wrapper.emitted('select')).toBeUndefined();
    });
});

describe('KaleidoscopeTab', function() {
    it('opens from the keyboard', async function() {
        const wrapper = mount(KaleidoscopeTab);
        const tab = wrapper.get('[data-ks="tab"]');

        expect(tab.attributes('role')).toBe('button');
        expect(tab.attributes('tabindex')).toBe('0');

        await tab.trigger('keydown', { key: 'Enter' });
        await tab.trigger('keydown', { key: ' ' });
        await tab.trigger('keydown', { key: 'a' });

        expect(wrapper.emitted('open')).toEqual([[], []]);
    });
});

describe('KaleidoscopeStrip gestures', function() {
    it('allows moving a dragged row and collapses from its title', async function() {
        const wrapper = mount(KaleidoscopeStrip, { props: { panels: panels_built() } });
        const transfer = { effectAllowed: 'none' };

        await wrapper.get('[data-ks-row="timer"]').trigger('dragstart', { dataTransfer: transfer });

        expect(transfer.effectAllowed).toBe('move');

        await wrapper.get('span.cursor-pointer').trigger('click');

        expect(wrapper.emitted('close')).toHaveLength(1);
    });

    it('places panels missing from the saved order after the ordered ones', function() {
        const cases: [string[], string[]][] = [
            [['queries'], ['queries', 'timer']],
            [['timer'], ['timer', 'queries']],
        ];

        for (const [order, expected] of cases) {
            const props = { panel_order: order, panels: panels_built() };
            const wrapper = mount(KaleidoscopeStrip, { props });
            const rows = wrapper.findAll('[data-ks-row]').map(function(row) {
                return row.attributes('data-ks-row');
            });

            expect(rows).toEqual(expected);
        }
    });

    it('ignores a drop whose dragged row vanished in the meantime', async function() {
        const wrapper = mount(KaleidoscopeStrip, { props: { panels: panels_built() } });

        await wrapper.get('[data-ks-row="queries"]').trigger('dragstart', { dataTransfer: null });
        await wrapper.setProps({ panels: panels_built().slice(0, 1) });
        await wrapper.get('[data-ks-row="timer"]').trigger('drop');

        expect(wrapper.emitted('reorder')).toBeUndefined();
    });
});

describe('KaleidoscopeStrip contract', function() {
    it('refuses a panel index outside its rows', function() {
        const wrapper = mount(KaleidoscopeStrip, { props: { panels: panels_built() } });
        const strip = wrapper.vm as unknown as StripInternals;
        const event = new Event('dragover') as DragEvent;

        expect(function() { strip.on_drag_start(0.5, event); }).toThrow(TypeError);
        expect(function() { strip.on_drag_over(-1, event); }).toThrow(RangeError);
        expect(function() { strip.on_drop(2); }).toThrow('a panel index must be below 2: 2');
    });
});

describe('KaleidoscopeTab gestures', function() {
    it('opens on a short touch', async function() {
        const wrapper = mount(KaleidoscopeTab);
        const touches = [{ clientY: 300 } as Touch];
        const start = new TouchEvent('touchstart', { cancelable: true, touches: touches });

        (wrapper.element as HTMLElement).dispatchEvent(start);
        document.dispatchEvent(new TouchEvent('touchend', { touches: [] }));
        await flushPromises();

        expect(wrapper.emitted('open')).toHaveLength(1);

        wrapper.unmount();
    });
});
