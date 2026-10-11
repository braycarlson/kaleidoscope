const TOOLBAR_PREFIX = '/__kaleidoscope__';

type RequestTracked = XMLHttpRequest & { _ks_url?: string };

function url_of(input: RequestInfo | URL): string {
    if (typeof input === 'string') return input;
    if (input instanceof URL) return input.href;
    return input.url;
}

function url_is_toolbar(url: string): boolean {
    try {
        return new URL(url, window.location.href).pathname.startsWith(TOOLBAR_PREFIX);
    } catch {
        return url.startsWith(TOOLBAR_PREFIX);
    }
}

export function use_interceptors(on_activity: () => void): () => void {
    const open_original = XMLHttpRequest.prototype.open;
    const send_original = XMLHttpRequest.prototype.send;
    const fetch_original = window.fetch;

    function activity_report() {
        on_activity();
    }

    function open_tracked(this: RequestTracked, ...args: unknown[]) {
        this._ks_url = String(args[1]);

        (open_original as (...args: unknown[]) => void).apply(this, args);
    }

    function send_tracked(this: RequestTracked, body?: Document | XMLHttpRequestBodyInit | null) {
        const ks_url = this._ks_url;

        if (ks_url !== undefined) {
            if (!url_is_toolbar(ks_url)) {
                this.addEventListener('loadend', activity_report, { once: true });
            }
        }

        send_original.call(this, body);
    }

    function fetch_tracked(input: RequestInfo | URL, init?: RequestInit) {
        const pending = fetch_original.call(window, input, init);

        if (url_is_toolbar(url_of(input))) {
            return pending;
        }

        return pending.then(function(response) {
            on_activity();

            return response;
        });
    }

    XMLHttpRequest.prototype.open = open_tracked;
    XMLHttpRequest.prototype.send = send_tracked;
    window.fetch = fetch_tracked;

    return function cleanup() {
        XMLHttpRequest.prototype.open = open_original;
        XMLHttpRequest.prototype.send = send_original;
        window.fetch = fetch_original;
    };
}
