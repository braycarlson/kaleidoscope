export function use_interceptors(on_activity: () => void): () => void {
    const open_original = XMLHttpRequest.prototype.open;
    const send_original = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(
        this: XMLHttpRequest & { _ks_url?: string },
        method: string,
        url: string | URL,
        async_flag?: boolean,
        username?: string | null,
        password?: string | null,
    ) {
        this._ks_url = String(url);
        return open_original.call(this, method, url, async_flag ?? true, username ?? null, password ?? null);
    };

    XMLHttpRequest.prototype.send = function(
        this: XMLHttpRequest & { _ks_url?: string },
        body?: Document | XMLHttpRequestBodyInit | null,
    ) {
        const ks_url = this._ks_url;

        this.addEventListener('loadend', function() {
            if (ks_url && !ks_url.startsWith('/__kaleidoscope__')) {
                on_activity();
            }
        });

        return send_original.call(this, body);
    };

    const fetch_original = window.fetch;

    window.fetch = function(input: RequestInfo | URL, init?: RequestInit) {
        const url = String(input);

        if (url.startsWith('/__kaleidoscope__')) {
            return fetch_original.call(this, input, init);
        }

        return fetch_original.call(this, input, init).then(function(response) {
            on_activity();
            return response;
        });
    };

    return function cleanup() {
        XMLHttpRequest.prototype.open = open_original;
        XMLHttpRequest.prototype.send = send_original;
        window.fetch = fetch_original;
    };
}
