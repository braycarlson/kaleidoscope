import { ref, onMounted, onUnmounted } from 'vue';
import { MOBILE_BREAKPOINT_PX } from '../constants';

export function use_mobile() {
    const is_mobile = ref(false);

    function check() {
        is_mobile.value = window.innerWidth < MOBILE_BREAKPOINT_PX;
    }

    onMounted(function() {
        check();
        window.addEventListener('resize', check);
    });

    onUnmounted(function() {
        window.removeEventListener('resize', check);
    });

    return { is_mobile };
}
