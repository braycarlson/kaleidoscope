const TOOLBAR_URL_PREFIX = '/__kaleidoscope__/';
const fetch_native = window.fetch.bind(window);

export function json_fetch<T = unknown>(url: string): Promise<T> {
    if (!url.startsWith(TOOLBAR_URL_PREFIX)) {
        throw new RangeError('a toolbar url must start with ' + TOOLBAR_URL_PREFIX + ': ' + url);
    }

    return fetch_native(url).then(function(response) {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return response.json();
    });
}

export { fetch_native };
