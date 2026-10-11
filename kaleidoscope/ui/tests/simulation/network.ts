import fc from 'fast-check';
import { CONTRACT, contract_arbitrary, type ContractEntry } from '../support/contract';
import { json_response } from '../support/fetch';
import type { Rng } from './rng';

export interface Exchange {
    body: unknown;
    dropped: boolean;
    id: number;
    reject: (error: Error) => void;
    resolve: (response: Response) => void;
    status: number;
    url: string;
}

export interface Faults {
    drop: number;
    error: number;
}

export interface Server {
    data_latest: Record<string, unknown>;
    enabled: Record<string, boolean>;
    flip: (panel_id: string) => void;
    handle: (url: string, failing: boolean) => [number, unknown];
}

export interface Network {
    deliver: (index: number) => void;
    faults: Faults;
    fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
    pending: Exchange[];
    server: Server;
}

export const PANEL_IDS = Object.freeze([
    'timer',
    'versions',
    'request',
    'queries',
    'templates',
    'cache',
    'staticfiles',
    'signals',
    'settings',
    'memory',
    'profiling',
    'line_profiling',
] as const);

export const PANEL_IDS_ISOLATED = Object.freeze(['line_profiling', 'memory', 'profiling']);
const PATH_ACTION = /^\/__kaleidoscope__\/panels\/queries\/action\/([^/]+)\/$/;
const PATH_PANEL = /^\/__kaleidoscope__\/panels\/([^/]+)\/(data|disable|enable)\/$/;
const PATH_QUERY_EXPLAIN = '/__kaleidoscope__/panels/queries/action/explain/';
const PATH_TEMPLATE_VALUE = '/__kaleidoscope__/panels/templates/action/value/';
const PENDING_MAX = 10_000;
const SAMPLES_PER_PANEL = 6;

function url_of(input: RequestInfo | URL): string {
    if (typeof input === 'string') return input;
    if (input instanceof URL) return input.href;
    return input.url;
}

function samples_create(rng: Rng): Record<string, unknown[]> {
    const samples: Record<string, unknown[]> = {};

    for (const panel_id of PANEL_IDS) {
        const entry = CONTRACT.panels[panel_id];

        if (entry === undefined) throw new Error('the contract has no entry for ' + panel_id);

        const arbitrary = contract_arbitrary(entry);
        const seed = rng.integer(0, 2 ** 30);

        samples[panel_id] = fc.sample(arbitrary, { numRuns: SAMPLES_PER_PANEL, seed });
    }

    return samples;
}

function answers_create(rng: Rng, entry: ContractEntry): () => unknown {
    const seed = rng.integer(0, 2 ** 30);
    const arbitrary = contract_arbitrary(entry);
    const answers = fc.sample(arbitrary, { numRuns: SAMPLES_PER_PANEL, seed: seed });
    let count = 0;

    return function answer_next(): unknown {
        count += 1;

        return answers[count % SAMPLES_PER_PANEL];
    };
}

function enabled_set(enabled: Record<string, boolean>, panel_id: string, value: boolean) {
    if (value) {
        if (PANEL_IDS_ISOLATED.includes(panel_id)) {
            for (const isolated of PANEL_IDS_ISOLATED) {
                enabled[isolated] = false;
            }
        }
    }

    enabled[panel_id] = value;
}

function panels_listed(
    enabled: Record<string, boolean>,
    versions: Record<string, number>,
): unknown[] {
    return PANEL_IDS.map(function(panel_id) {
        return {
            enabled: enabled[panel_id],
            id: panel_id,
            isolate: PANEL_IDS_ISOLATED.includes(panel_id),
            summary: 'version ' + (versions[panel_id] ?? 0),
            title: 'Panel ' + panel_id,
        };
    });
}

function server_create(rng: Rng): Server {
    const enabled: Record<string, boolean> = {};
    const samples = samples_create(rng);
    const versions: Record<string, number> = {};
    const data_latest: Record<string, unknown> = {};
    const template_value_next = answers_create(rng, CONTRACT.template_value);
    const query_explain_next = answers_create(rng, CONTRACT.query_explain);

    for (const panel_id of PANEL_IDS) {
        enabled[panel_id] = !PANEL_IDS_ISOLATED.includes(panel_id);
        versions[panel_id] = 0;
    }

    function panel_handle(panel_id: string, verb: string): [number, unknown] {
        if (!Object.hasOwn(enabled, panel_id)) return [404, { error: 'unknown panel' }];

        if (verb === 'data') {
            const version = (versions[panel_id] ?? 0) + 1;
            const sample = samples[panel_id]?.[version % SAMPLES_PER_PANEL];

            if (sample === undefined) throw new Error('the server has no sample for ' + panel_id);

            versions[panel_id] = version;

            const body: unknown = JSON.parse(JSON.stringify(sample));

            data_latest[panel_id] = body;

            return [200, body];
        }

        enabled_set(enabled, panel_id, verb === 'enable');

        return [200, { enabled: enabled[panel_id] }];
    }

    function handle(url: string, failing: boolean): [number, unknown] {
        const path = new URL(url, 'http://localhost:3000').pathname;

        if (!path.startsWith('/__kaleidoscope__/')) return [200, { activity: true }];
        if (failing) return [500, { error: 'simulated server failure' }];
        if (path === '/__kaleidoscope__/panels/') {
            return [200, { panels: panels_listed(enabled, versions) }];
        }

        if (path === PATH_TEMPLATE_VALUE) return [200, template_value_next()];
        if (path === PATH_QUERY_EXPLAIN) return [200, query_explain_next()];

        const panel = PATH_PANEL.exec(path);

        if (panel) return panel_handle(panel[1] ?? '', panel[2] ?? '');

        const action = PATH_ACTION.exec(path);

        if (action) return [200, { success: true }];

        return [404, { error: 'not found' }];
    }

    function flip(panel_id: string) {
        enabled_set(enabled, panel_id, !enabled[panel_id]);
    }

    return { data_latest, enabled, flip, handle };
}

export function network_create(rng: Rng, faults_initial: Faults): Network {
    const faults: Faults = { ...faults_initial };
    const pending: Exchange[] = [];
    const server = server_create(rng);
    let exchange_count = 0;

    function fetch(input: RequestInfo | URL, _init?: RequestInit): Promise<Response> {
        const url = url_of(input);
        const toolbar = url.includes('/__kaleidoscope__/');
        const failing = toolbar && rng.chance(faults.error);
        const [status, body] = server.handle(url, failing);
        const dropped = !failing && rng.chance(faults.drop);

        if (pending.length >= PENDING_MAX) {
            throw new Error('the simulated network holds too many pending requests');
        }

        exchange_count += 1;

        const id = exchange_count;

        return new Promise(function(resolve, reject) {
            pending.push({ body, dropped, id, reject, resolve, status, url });
        });
    }

    function deliver(index: number) {
        const [exchange] = pending.splice(index, 1);

        if (exchange === undefined) throw new Error('deliver was given an index with no exchange');

        if (exchange.dropped) {
            exchange.reject(new TypeError('Failed to fetch'));

            return;
        }

        exchange.resolve(json_response(exchange.status, exchange.body));
    }

    return { deliver, faults, fetch, pending, server };
}
