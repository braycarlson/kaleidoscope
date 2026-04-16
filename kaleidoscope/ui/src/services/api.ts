const fetch_native = window.fetch.bind(window);

export function json_fetch<T = unknown>(url: string): Promise<T> {
    return fetch_native(url).then(function(response) {
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return response.json();
    });
}

export { fetch_native };
