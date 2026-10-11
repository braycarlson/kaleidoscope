import { beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest';
import { defineComponent, h } from 'vue';
import { mount } from '@vue/test-utils';
import { use_drag } from '../../src/composables/use_drag';
import { TAB_HEIGHT_PX } from '../../src/constants';

type Drag = ReturnType<typeof use_drag>;

interface DragMounted {
    drag: Drag;
    unmount: () => void;
}

const POSITIONS_UNFIT = Object.freeze(['-5', 'NaN', 'abc', '100000']);
const STORAGE_KEY = 'kaleidoscope_tab_top';

function host_render() {
    return h('div');
}

function window_height_set(height: number) {
    const descriptor = { configurable: true, value: height, writable: true };

    Object.defineProperty(window, 'innerHeight', descriptor);
}

function drag_mount(on_click: () => void): DragMounted {
    let drag: Drag | null = null;
    let mounted = true;

    const Host = defineComponent({
        setup() {
            drag = use_drag(on_click);

            return host_render;
        },
    });

    const wrapper = mount(Host);

    function unmount() {
        if (!mounted) return;

        mounted = false;
        wrapper.unmount();
    }

    onTestFinished(unmount);

    return { drag: drag as unknown as Drag, unmount };
}

function mouse(type: string, client_y: number): MouseEvent {
    return new MouseEvent(type, { bubbles: true, cancelable: true, clientY: client_y });
}

function touch(type: string, client_ys: number[]): TouchEvent {
    const touches = client_ys.map(function(client_y) { return { clientY: client_y } as Touch; });

    return new TouchEvent(type, { cancelable: true, touches });
}

beforeEach(function() {
    localStorage.clear();
    window_height_set(800);
});

describe('use_drag stored position', function() {
    it('starts in the middle without a stored position', function() {
        const { drag } = drag_mount(vi.fn());

        expect(drag.tab_top.value).toBe(400);
    });

    it('restores a stored position that fits the window', function() {
        localStorage.setItem(STORAGE_KEY, '120');

        expect(drag_mount(vi.fn()).drag.tab_top.value).toBe(120);
    });

    it('keeps the fallback inside a window shorter than twice the tab', function() {
        window_height_set(100);

        expect(drag_mount(vi.fn()).drag.tab_top.value).toBe(100 - TAB_HEIGHT_PX);
    });

    it.each(POSITIONS_UNFIT)('ignores a stored position that does not fit: %s', function(stored) {
        localStorage.setItem(STORAGE_KEY, stored);

        expect(drag_mount(vi.fn()).drag.tab_top.value).toBe(400);
    });
});

describe('use_drag dragging', function() {
    it('moves the tab with the pointer and saves where it stops', function() {
        const click = vi.fn();
        const { drag } = drag_mount(click);

        drag.on_mousedown(mouse('mousedown', 400));

        expect(drag.dragging.value).toBe(true);

        document.dispatchEvent(mouse('mousemove', 300));
        document.dispatchEvent(mouse('mouseup', 300));

        expect(drag.tab_top.value).toBe(300);
        expect(drag.dragging.value).toBe(false);
        expect(localStorage.getItem(STORAGE_KEY)).toBe('300');
        expect(click).not.toHaveBeenCalled();
    });

    it('keeps the tab inside the window while dragging', function() {
        const { drag } = drag_mount(vi.fn());

        drag.on_mousedown(mouse('mousedown', 400));
        document.dispatchEvent(mouse('mousemove', -1000));

        expect(drag.tab_top.value).toBe(0);

        document.dispatchEvent(mouse('mousemove', 5000));

        expect(drag.tab_top.value).toBe(800 - TAB_HEIGHT_PX);

        document.dispatchEvent(mouse('mouseup', 5000));
    });

    it('treats a press without movement as a click', function() {
        const click = vi.fn();
        const { drag } = drag_mount(click);

        drag.on_mousedown(mouse('mousedown', 400));
        document.dispatchEvent(mouse('mousemove', 402));
        document.dispatchEvent(mouse('mouseup', 402));

        expect(click).toHaveBeenCalledTimes(1);
    });

    it('stops following the pointer after the press ends', function() {
        const { drag } = drag_mount(vi.fn());

        drag.on_mousedown(mouse('mousedown', 400));
        document.dispatchEvent(mouse('mouseup', 400));
        document.dispatchEvent(mouse('mousemove', 100));

        expect(drag.tab_top.value).toBe(400);
    });

});

describe('use_drag touches', function() {
    it('follows touches the same way as the mouse', function() {
        const click = vi.fn();
        const { drag } = drag_mount(click);

        drag.on_touchstart(touch('touchstart', [400]));
        document.dispatchEvent(touch('touchmove', [250]));
        document.dispatchEvent(touch('touchend', []));

        expect(drag.tab_top.value).toBe(250);
        expect(click).not.toHaveBeenCalled();
    });

    it('ignores touch events that carry no touch', function() {
        const click = vi.fn();
        const { drag } = drag_mount(click);

        drag.on_touchstart(touch('touchstart', []));

        expect(drag.dragging.value).toBe(false);

        drag.on_touchstart(touch('touchstart', [400]));
        document.dispatchEvent(touch('touchmove', []));
        document.dispatchEvent(touch('touchend', []));

        expect(drag.tab_top.value).toBe(400);
        expect(click).toHaveBeenCalledTimes(1);
    });
});

describe('use_drag lifecycle', function() {
    it('pulls the tab back inside when the window shrinks', function() {
        localStorage.setItem(STORAGE_KEY, '700');

        const { drag } = drag_mount(vi.fn());

        window_height_set(300);
        window.dispatchEvent(new Event('resize'));

        expect(drag.tab_top.value).toBe(300 - TAB_HEIGHT_PX);
    });

    it('stops listening once unmounted', function() {
        const { drag, unmount } = drag_mount(vi.fn());

        drag.on_mousedown(mouse('mousedown', 400));
        unmount();
        document.dispatchEvent(mouse('mousemove', 100));

        expect(drag.tab_top.value).toBe(400);
    });
});
