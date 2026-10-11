export function storage_read(key: string): string | null {
    if (key === '') throw new RangeError('a storage key must not be empty');

    try {
        return localStorage.getItem(key);
    } catch {
        return null;
    }
}

export function storage_write(key: string, value: string): boolean {
    if (key === '') throw new RangeError('a storage key must not be empty');

    try {
        localStorage.setItem(key, value);
    } catch {
        return false;
    }

    return true;
}
