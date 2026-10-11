function clipboard_fallback(text: string): Promise<void> {
    const area = document.createElement('textarea');

    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();

    let copied: boolean;

    try {
        copied = document.execCommand('copy');
    } catch {
        copied = false;
    } finally {
        area.remove();
    }

    if (!copied) {
        return Promise.reject(new Error('The browser refused to copy'));
    }

    return Promise.resolve();
}

function clipboard_of(): Clipboard | undefined {
    return navigator.clipboard;
}

export function clipboard_write(text: string): Promise<void> {
    const clipboard = clipboard_of();

    if (clipboard === undefined) return clipboard_fallback(text);
    if (typeof clipboard.writeText !== 'function') return clipboard_fallback(text);

    return clipboard.writeText(text).catch(function() {
        return clipboard_fallback(text);
    });
}
