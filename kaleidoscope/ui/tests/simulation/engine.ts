import fc from 'fast-check';
import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils';
import { isDeepStrictEqual } from 'node:util';
import { vi } from 'vitest';
import type { Component } from 'vue';
import { DEBOUNCE_MS } from '../../src/constants';
import { TEXT_ARBITRARY, texts_unsafe } from '../support/contract';
import { vue_reports } from '../support/setup';
import { network_create, PANEL_IDS, type Faults, type Network } from './network';
import { rng_create, type Rng } from './rng';

interface AppInternals {
    panel_active: string | null;
    panel_data: unknown;
    panel_error: string | null;
    panels_available: { id: string; title: string }[];
    panels_disabled: Record<string, boolean>;
    side: string;
    state: string;
}

interface Context {
    App: Component;
    delivered_max: Record<string, number>;
    journal: string[];
    network: Network;
    rng: Rng;
    sometimes: Record<string, number>;
    step: number;
    wrapper: VueWrapper | null;
}

type Action = (context: Context) => Promise<void>;

export const SOMETIMES_TARGETS = Object.freeze([
    'activity refreshed the toolbar',
    'data delivered out of order',
    'external toggle mirrored',
    'mobile layout',
    'panel error shown',
    'panel interacted',
    'panel opened',
    'remounted with a panel open',
    'reordered',
    'request dropped',
    'server error answered',
    'storage corrupted before a remount',
    'toggle pressed',
] as const);

const CHECKPOINT_EVERY = 20;
const DELIVERIES_PER_ROUND_MAX = 10_000;
const JOURNAL_TAIL = 40;
const PANEL_CLICKABLE = 'button, th, tr, td, span, div.cursor-pointer';
const SETTLE_ROUNDS_MAX = 50;
const STATES: readonly string[] = Object.freeze(['collapsed', 'panel', 'strip']);

const STORAGE_GARBAGE = Object.freeze([
    '',
    'null',
    '[]',
    'not json',
    '{"state":"panel","active_panel":"constructor"}',
    '{"side":"up","order":[1,2,2],"state":"strip"}',
    '{"disabled":{"queries":"yes","__proto__":true},"state":"strip"}',
]);

const STORAGE_KEY = 'kaleidoscope_preferences';

function wrapper_of(context: Context): VueWrapper {
    if (context.wrapper === null) throw new Error('the app is not mounted');

    return context.wrapper;
}

function internals(context: Context): AppInternals {
    return wrapper_of(context).vm as unknown as AppInternals;
}

function journal(context: Context, line: string) {
    context.journal.push('step ' + context.step + ': ' + line);
}

function sometimes(context: Context, name: string, condition: boolean) {
    const count = context.sometimes[name] ?? 0;

    context.sometimes[name] = condition ? count + 1 : count;
}

function width_set(width: number) {
    const descriptor = { configurable: true, value: width, writable: true };

    Object.defineProperty(window, 'innerWidth', descriptor);
}

function check(context: Context, condition: boolean, message: string) {
    if (condition) return;

    const tail = context.journal.slice(-JOURNAL_TAIL).join('\n');
    const prefix = 'seed ' + context.rng.seed + ' step ' + context.step;

    throw new Error(prefix + ': ' + message + '\n' + tail);
}

async function app_mount(context: Context) {
    context.wrapper = mount(context.App, { attachTo: document.body });
    await flushPromises();
}

async function click(context: Context, selector: string): Promise<boolean> {
    const targets = wrapper_of(context).findAll(selector);

    if (targets.length === 0) return false;

    const target = context.rng.choice(targets);
    const label = target.attributes('data-ks-panel') ?? target.attributes('data-ks-toggle') ?? '';

    journal(context, 'click ' + selector + ' ' + label);
    await target.trigger('click');
    await flushPromises();

    return true;
}

async function deliver(context: Context, index: number) {
    const exchange = context.network.pending[index];

    if (exchange === undefined) throw new Error('deliver was given an index with no exchange');

    const newest = context.delivered_max[exchange.url] ?? 0;
    const out_of_order = exchange.url.includes('/data/') && exchange.id < newest;
    const outcome = exchange.dropped ? 'dropped' : exchange.status;

    sometimes(context, 'data delivered out of order', out_of_order);
    sometimes(context, 'request dropped', exchange.dropped);
    sometimes(context, 'server error answered', exchange.status === 500);

    context.delivered_max[exchange.url] = Math.max(newest, exchange.id);
    journal(context, 'deliver #' + exchange.id + ' ' + exchange.url + ' ' + outcome);
    context.network.deliver(index);
    await flushPromises();
}

async function settle(context: Context) {
    for (let round = 0; round < SETTLE_ROUNDS_MAX; round++) {
        for (let delivered = 0; delivered < DELIVERIES_PER_ROUND_MAX; delivered++) {
            if (context.network.pending.length === 0) break;

            await deliver(context, 0);
        }

        vi.advanceTimersByTime(DEBOUNCE_MS);
        await flushPromises();

        if (context.network.pending.length === 0) break;
    }
}

async function panel_type(context: Context, inputs: DOMWrapper<Element>[]) {
    const seed = context.rng.integer(0, 2 ** 30);
    const text = fc.sample(TEXT_ARBITRARY, { numRuns: 1, seed: seed })[0] ?? '';

    journal(context, 'type ' + JSON.stringify(text) + ' into the panel');
    await context.rng.choice(inputs).setValue(text);
    await flushPromises();
    sometimes(context, 'panel interacted', true);
}

async function action_activity(context: Context) {
    journal(context, 'page activity');
    window.fetch('/api/activity/' + context.step).catch(function() { return undefined; });
    await flushPromises();
}

async function action_debounce(context: Context) {
    journal(context, 'debounce elapses');
    vi.advanceTimersByTime(DEBOUNCE_MS);
    await flushPromises();
}

async function action_deliver(context: Context) {
    const count = context.network.pending.length;

    if (count === 0) return;

    const index = context.rng.chance(0.5) ? count - 1 : context.rng.integer(0, count - 1);

    await deliver(context, index);
}

function action_external_flip(context: Context): Promise<void> {
    const panel_id = context.rng.choice(PANEL_IDS);

    journal(context, 'another tab flips ' + panel_id);
    context.network.server.flip(panel_id);

    return Promise.resolve();
}

async function action_panel_close(context: Context) {
    await click(context, '[data-ks="panel-close"]');
}

async function action_panel_interact(context: Context) {
    const panel = wrapper_of(context).find('[data-ks="panel"] > .overflow-y-auto');

    if (!panel.exists()) return;

    const inputs = panel.findAll('input');
    const typing = context.rng.chance(0.25);

    if (inputs.length > 0) {
        if (typing) {
            await panel_type(context, inputs);

            return;
        }
    }

    const targets = panel.findAll(PANEL_CLICKABLE);

    if (targets.length === 0) return;

    const target = context.rng.choice(targets);
    const label = target.element.tagName + ' ' + target.text().slice(0, 40);

    journal(context, 'click inside the panel on ' + label);
    await target.trigger('click');
    await flushPromises();
    sometimes(context, 'panel interacted', true);
}

async function action_panel_select(context: Context) {
    const clicked = await click(context, '[data-ks-panel]');

    sometimes(context, 'panel opened', clicked && internals(context).state === 'panel');
}

async function action_panel_toggle(context: Context) {
    const clicked = await click(context, '[data-ks-toggle]');

    sometimes(context, 'toggle pressed', clicked);
}

async function action_remount(context: Context) {
    const open = internals(context).state === 'panel';

    journal(context, 'remount');
    wrapper_of(context).unmount();
    await app_mount(context);
    sometimes(context, 'remounted with a panel open', open && internals(context).state === 'panel');
}

async function action_reorder(context: Context) {
    const rows = wrapper_of(context).findAll('[data-ks-row]');

    if (rows.length < 2) return;

    const source = context.rng.choice(rows);
    const target = context.rng.choice(rows);
    const row_source = source.attributes('data-ks-row') ?? '';
    const row_target = target.attributes('data-ks-row') ?? '';

    journal(context, 'drag ' + row_source + ' onto ' + row_target);
    await source.trigger('dragstart');
    await target.trigger('dragover');
    await target.trigger('drop');
    await source.trigger('dragend');
    sometimes(context, 'reordered', source.element !== target.element);
}

async function action_resize(context: Context) {
    const width = context.rng.choice([420, 1280]);

    journal(context, 'resize to ' + width);
    width_set(width);
    window.dispatchEvent(new Event('resize'));
    await flushPromises();
    sometimes(context, 'mobile layout', width < 640 && internals(context).state !== 'collapsed');
}

async function action_storage_corrupt(context: Context) {
    const garbage = context.rng.choice(STORAGE_GARBAGE);

    journal(context, 'storage corrupted with ' + JSON.stringify(garbage));
    localStorage.setItem(STORAGE_KEY, garbage);

    if (context.rng.chance(0.5)) {
        await action_remount(context);
        sometimes(context, 'storage corrupted before a remount', true);
    }
}

async function action_strip_close(context: Context) {
    await click(context, '[data-ks="collapse"], [data-ks="strip-close"]');
}

async function action_swap(context: Context) {
    await click(context, '[data-ks="swap"]');
}

async function action_tab_open(context: Context) {
    const tab = wrapper_of(context).find('[data-ks="tab"]');

    if (!tab.exists()) return;

    journal(context, 'press the tab');
    await tab.trigger('mousedown', { clientY: 300 });
    document.dispatchEvent(new MouseEvent('mouseup', { clientY: 300 }));
    await flushPromises();
}

async function action_theme(context: Context) {
    await click(context, '[data-ks="theme"]');
}

const ACTIONS: readonly [Action, number][] = Object.freeze([
    [action_activity, 4],
    [action_debounce, 3],
    [action_deliver, 6],
    [action_external_flip, 1],
    [action_panel_close, 1],
    [action_panel_interact, 4],
    [action_panel_select, 5],
    [action_panel_toggle, 3],
    [action_remount, 1],
    [action_reorder, 1],
    [action_resize, 1],
    [action_storage_corrupt, 1],
    [action_strip_close, 1],
    [action_swap, 1],
    [action_tab_open, 4],
    [action_theme, 1],
]);

const ACTIONS_WEIGHTED: Action[] = ACTIONS.flatMap(function([action, weight]) {
    return Array.from({ length: weight }, function() { return action; });
});

function invariants_step(context: Context) {
    const app = internals(context);
    const reports = vue_reports.splice(0);
    const wrapper = wrapper_of(context);
    const collapsed = app.state === 'collapsed';
    const tab_shown = wrapper.find('[data-ks="tab"]').exists();
    const strip_shown = wrapper.find('[data-ks="strip"], [data-ks="panel"]').exists();

    const unsafe = texts_unsafe(wrapper.element as Element);

    sometimes(context, 'panel error shown', app.panel_error !== null);
    check(context, reports.length === 0, 'Vue reported: ' + reports.join('\n'));
    check(context, unsafe.length === 0, 'the toolbar shows broken text: ' + unsafe.join(' | '));
    check(context, STATES.includes(app.state), 'unknown state ' + app.state);
    check(context, ['left', 'right'].includes(app.side), 'unknown side ' + app.side);
    check(context, collapsed === tab_shown, 'the tab disagrees with state ' + app.state);
    check(context, collapsed !== strip_shown, 'the strip disagrees with state ' + app.state);

    if (app.panel_active !== null) {
        const known = (PANEL_IDS as readonly string[]).includes(app.panel_active);

        check(context, known, 'unknown active panel ' + app.panel_active);
    }
}

async function invariants_checkpoint(context: Context) {
    const faults = { ...context.network.faults };

    context.network.faults.drop = 0;
    context.network.faults.error = 0;

    try {
        await settle(context);
        await action_activity(context);
        await settle(context);
        invariants_settled(context);
    } finally {
        context.network.faults.drop = faults.drop;
        context.network.faults.error = faults.error;
    }
}

function invariants_settled(context: Context) {
    const app = internals(context);
    const server = context.network.server;
    const listed = app.panels_available.map(function(panel) { return panel.id; });
    const listed_match = isDeepStrictEqual(listed, [...PANEL_IDS]);

    sometimes(context, 'activity refreshed the toolbar', listed.length > 0);
    check(context, listed_match, 'the panel list disagrees with the server: ' + listed.join(','));

    for (const panel_id of PANEL_IDS) {
        const mirrored = app.panels_disabled[panel_id] === !server.enabled[panel_id];

        check(context, mirrored, panel_id + ' enabled disagrees with the server after settling');
    }

    sometimes(context, 'external toggle mirrored', true);

    if (app.state !== 'panel') return;
    if (app.panel_active === null) return;

    const error = app.panel_error;
    const latest = server.data_latest[app.panel_active];
    const data_current = isDeepStrictEqual(app.panel_data, latest);

    check(context, error === null, 'a settled panel still shows an error: ' + (error ?? ''));
    check(context, data_current, app.panel_active + ' shows stale data after settling');
}

export async function simulation_run(
    seed: number,
    step_count: number,
    faults: Faults,
): Promise<Record<string, number>> {
    const rng = rng_create(seed);
    const network = network_create(rng, faults);

    localStorage.clear();
    width_set(1280);
    vi.stubGlobal('fetch', network.fetch);
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.resetModules();

    const module = await import('../../src/App.vue');

    const context: Context = {
        App: module.default,
        delivered_max: {},
        journal: [],
        network: network,
        rng: rng,
        sometimes: {},
        step: 0,
        wrapper: null,
    };

    for (const target of SOMETIMES_TARGETS) {
        sometimes(context, target, false);
    }

    try {
        await app_mount(context);

        for (let step = 0; step < step_count; step++) {
            context.step = step;
            await rng.choice(ACTIONS_WEIGHTED)(context);
            invariants_step(context);

            if ((step + 1) % CHECKPOINT_EVERY === 0) {
                await invariants_checkpoint(context);
            }
        }
    } finally {
        if (context.wrapper) {
            context.wrapper.unmount();
        }

        vi.useRealTimers();
    }

    return context.sometimes;
}
