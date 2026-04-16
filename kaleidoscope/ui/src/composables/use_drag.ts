import { ref, onUnmounted, type Ref } from 'vue';
import { TAB_HEIGHT_PX, DRAG_CLICK_THRESHOLD_PX } from '../constants';

interface UseDragReturn {
    tab_top: Ref<number>;
    dragging: Ref<boolean>;
    on_mousedown: (event: MouseEvent) => void;
    on_touchstart: (event: TouchEvent) => void;
}

function tab_top_load(): number {
    try {
        const stored = localStorage.getItem('kaleidoscope_tab_top');

        if (stored !== null) {
            const parsed = parseFloat(stored);

            if (!isNaN(parsed) && parsed >= 0 && parsed <= window.innerHeight - TAB_HEIGHT_PX) {
                return parsed;
            }
        }
    } catch {
        // localStorage may be unavailable
    }

    return window.innerHeight / 2;
}

function tab_top_save(value: number): void {
    try {
        localStorage.setItem('kaleidoscope_tab_top', String(value));
    } catch {
        // localStorage may be unavailable
    }
}

export function use_drag(on_click: () => void): UseDragReturn {
    const tab_top = ref(tab_top_load());
    const dragging = ref(false);

    let start_y = 0;
    let top_start = 0;
    let distance_moved = 0;

    function on_mousemove(event: MouseEvent) {
        drag_update(event.clientY);
    }

    function on_mouseup() {
        document.removeEventListener('mousemove', on_mousemove);
        document.removeEventListener('mouseup', on_mouseup);
        drag_end();
    }

    function on_touchmove(event: TouchEvent) {
        drag_update(event.touches[0].clientY);
        event.preventDefault();
    }

    function on_touchend() {
        document.removeEventListener('touchmove', on_touchmove);
        document.removeEventListener('touchend', on_touchend);
        drag_end();
    }

    function on_mousedown(event: MouseEvent) {
        drag_start(event.clientY);
        document.addEventListener('mousemove', on_mousemove);
        document.addEventListener('mouseup', on_mouseup);
        event.preventDefault();
        event.stopPropagation();
    }

    function on_touchstart(event: TouchEvent) {
        drag_start(event.touches[0].clientY);
        document.addEventListener('touchmove', on_touchmove, { passive: false });
        document.addEventListener('touchend', on_touchend);
        event.preventDefault();
        event.stopPropagation();
    }

    function drag_start(y: number) {
        dragging.value = true;
        start_y = y;
        top_start = tab_top.value;
        distance_moved = 0;
    }

    function drag_update(y: number) {
        const delta = y - start_y;
        distance_moved = Math.abs(delta);
        const top_new = top_start + delta;
        tab_top.value = Math.max(0, Math.min(top_new, window.innerHeight - TAB_HEIGHT_PX));
    }

    function drag_end() {
        dragging.value = false;
        tab_top_save(tab_top.value);

        if (distance_moved < DRAG_CLICK_THRESHOLD_PX) {
            on_click();
        }
    }

    function cleanup() {
        document.removeEventListener('mousemove', on_mousemove);
        document.removeEventListener('mouseup', on_mouseup);
        document.removeEventListener('touchmove', on_touchmove);
        document.removeEventListener('touchend', on_touchend);
    }

    onUnmounted(cleanup);

    return { tab_top, dragging, on_mousedown, on_touchstart };
}
