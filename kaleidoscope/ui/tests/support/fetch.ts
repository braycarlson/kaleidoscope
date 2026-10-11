export interface PendingRequest {
    url: string;
    resolve: (status: number, body: unknown) => void;
    fail: (message: string) => void;
}

export interface FetchFake {
    calls: string[];
    pending: PendingRequest[];
    fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
    resolve_all: (answer: (url: string) => [number, unknown]) => number;
    take: (url_part: string) => PendingRequest;
}

const PENDING_MAX = 10_000;

function url_of(input: RequestInfo | URL): string {
    if (typeof input === 'string') return input;
    if (input instanceof URL) return input.href;
    return input.url;
}

export function json_response(status: number, body: unknown): Response {
    const text = typeof body === 'string' ? body : JSON.stringify(body);

    return new Response(text, {
        headers: { 'Content-Type': 'application/json' },
        status: status,
        statusText: status === 200 ? 'OK' : 'Error',
    });
}

export function fetch_fake_create(): FetchFake {
    const calls: string[] = [];
    const pending: PendingRequest[] = [];

    function fetch(input: RequestInfo | URL, _init?: RequestInit): Promise<Response> {
        const url = url_of(input);

        calls.push(url);

        if (pending.length >= PENDING_MAX) {
            throw new Error('the fake fetch holds too many pending requests');
        }

        return new Promise(function(resolve, reject) {
            function request_resolve(status: number, body: unknown) {
                resolve(json_response(status, body));
            }

            function request_fail(message: string) {
                reject(new TypeError(message));
            }

            const request: PendingRequest = { url, resolve: request_resolve, fail: request_fail };

            pending.push(request);
        });
    }

    function take(url_part: string): PendingRequest {
        const index = pending.findIndex(function(request) {
            return request.url.includes(url_part);
        });

        if (index === -1) {
            const urls = pending.map(function(request) { return request.url; }).join(', ');
            throw new Error('no pending request matches ' + url_part + ' among ' + urls);
        }

        const [request] = pending.splice(index, 1);

        if (request === undefined) {
            throw new Error('the pending request vanished while being taken');
        }

        return request;
    }

    function resolve_all(answer: (url: string) => [number, unknown]): number {
        let count = 0;

        while (count < PENDING_MAX) {
            const request = pending.shift();

            if (request === undefined) break;

            const [status, body] = answer(request.url);

            request.resolve(status, body);
            count += 1;
        }

        return count;
    }

    return { calls, pending, fetch, resolve_all, take };
}

export async function settled(): Promise<void> {
    for (let index = 0; index < 10; index++) {
        await new Promise(function(resolve) { setTimeout(resolve, 0); });
    }
}
