import { ref, onMounted, onUnmounted, type Ref } from 'vue';
import { TAB_HEIGHT_PX, DRAG_CLICK_THRESHOLD_PX } from '../constants';
import { storage_read, storage_write } from '../services/storage';

interface UseDragReturn {
    tab_top: Ref<number>;
    dragging: Ref<boolean>;
    on_mousedown: (event: MouseEvent) => void;
    on_touchstart: (event: TouchEvent) => void;
}

interface DragTracker {
    end: () => void;
    start: (y: number) => void;
    update: (y: number) => void;
}

const STORAGE_KEY = 'kaleidoscope_tab_top';

function tab_top_clamp(value: number): number {
    return Math.max(0, Math.min(value, window.innerHeight - TAB_HEIGHT_PX));
}

function tab_top_valid(value: number): boolean {
    if (isNaN(value)) return false;
    if (value < 0) return false;
    return value <= window.innerHeight - TAB_HEIGHT_PX;
}

function tab_top_load(): number {
    const fallback = tab_top_clamp(window.innerHeight / 2);
    const stored = storage_read(STORAGE_KEY);

    if (stored === null) return fallback;

    const parsed = parseFloat(stored);

    if (!tab_top_valid(parsed)) return fallback;

    return parsed;
}

function tab_top_save(value: number): void {
    void storage_write(STORAGE_KEY, String(value));
}

function drag_tracker_create(
    tab_top: Ref<number>,
    dragging: Ref<boolean>,
    on_click: () => void,
): DragTracker {
    let start_y = 0;
    let top_start = 0;
    let distance_moved = 0;

    function start(y: number) {
        dragging.value = true;
        start_y = y;
        top_start = tab_top.value;
        distance_moved = 0;
    }

    function update(y: number) {
        const delta = y - start_y;
        distance_moved = Math.abs(delta);
        tab_top.value = tab_top_clamp(top_start + delta);
    }

    function end() {
        dragging.value = false;
        tab_top_save(tab_top.value);

        if (distance_moved < DRAG_CLICK_THRESHOLD_PX) {
            on_click();
        }
    }

    return { end, start, update };
}

export function use_drag(on_click: () => void): UseDragReturn {
    const tab_top = ref(tab_top_load());
    const dragging = ref(false);
    const tracker = drag_tracker_create(tab_top, dragging, on_click);

    function on_mousemove(event: MouseEvent) {
        tracker.update(event.clientY);
    }

    function on_mouseup() {
        document.removeEventListener('mousemove', on_mousemove);
        document.removeEventListener('mouseup', on_mouseup);
        tracker.end();
    }

    function on_resize() {
        tab_top.value = tab_top_clamp(tab_top.value);
    }

    function on_touchmove(event: TouchEvent) {
        const touch = event.touches[0];

        if (touch === undefined) return;

        tracker.update(touch.clientY);
        event.preventDefault();
    }

    function on_touchend() {
        document.removeEventListener('touchmove', on_touchmove);
        document.removeEventListener('touchend', on_touchend);
        tracker.end();
    }

    function on_mousedown(event: MouseEvent) {
        tracker.start(event.clientY);
        document.addEventListener('mousemove', on_mousemove);
        document.addEventListener('mouseup', on_mouseup);
        event.preventDefault();
        event.stopPropagation();
    }

    function on_touchstart(event: TouchEvent) {
        const touch = event.touches[0];

        if (touch === undefined) return;

        tracker.start(touch.clientY);
        document.addEventListener('touchmove', on_touchmove, { passive: false });
        document.addEventListener('touchend', on_touchend);
        event.preventDefault();
        event.stopPropagation();
    }

    function cleanup() {
        document.removeEventListener('mousemove', on_mousemove);
        document.removeEventListener('mouseup', on_mouseup);
        document.removeEventListener('touchmove', on_touchmove);
        document.removeEventListener('touchend', on_touchend);
        window.removeEventListener('resize', on_resize);
    }

    onMounted(function() {
        window.addEventListener('resize', on_resize);
    });

    onUnmounted(cleanup);

    return { tab_top, dragging, on_mousedown, on_touchstart };
}
