import { ref } from 'vue';
import { storage_read, storage_write } from '../services/storage';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'ks-theme';
const theme = ref<Theme>(load_theme());

function load_theme(): Theme {
    const stored = storage_read(STORAGE_KEY);

    if (stored === 'dark') return stored;
    if (stored === 'light') return stored;
    return 'dark';
}

function save_theme(value: Theme) {
    void storage_write(STORAGE_KEY, value);
}

export function use_theme() {
    function toggle() {
        theme.value = theme.value === 'dark' ? 'light' : 'dark';
        save_theme(theme.value);
    }

    return { theme, toggle };
}
