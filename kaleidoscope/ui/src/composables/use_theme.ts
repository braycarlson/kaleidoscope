import { ref } from 'vue';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'ks-theme';

const theme = ref<Theme>(load_theme());

function load_theme(): Theme {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);

        if (stored === 'dark' || stored === 'light') {
            return stored;
        }
    } catch {
        // localStorage unavailable
    }

    return 'dark';
}

function save_theme(value: Theme) {
    try {
        localStorage.setItem(STORAGE_KEY, value);
    } catch {
        // localStorage unavailable
    }
}

export function use_theme() {
    function toggle() {
        theme.value = theme.value === 'dark' ? 'light' : 'dark';
        save_theme(theme.value);
    }

    return { theme, toggle };
}
