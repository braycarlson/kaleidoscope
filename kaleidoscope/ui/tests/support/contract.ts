import fc, { type Arbitrary } from 'fast-check';
import contract from '../contract/panels.json';

export interface Schema {
    additionalProperties?: Schema | boolean;
    items?: Schema;
    properties?: Record<string, Schema>;
    required?: string[];
    type?: string | string[];
}

export interface ContractEntry extends Schema {
    variants?: Schema[];
}

interface Contract {
    panel_list: ContractEntry;
    panels: Record<string, ContractEntry>;
    query_explain: ContractEntry;
    template_value: ContractEntry;
}

type BuiltArbitraries = Map<Schema, Arbitrary<unknown>>;
type StackEntry = [unknown, Schema, string];

export const CONTRACT = contract as unknown as Contract;
const ERRORS_MAX = 50;
const KEY_ARBITRARY = fc.string({ maxLength: 8, minLength: 1 }).filter(text_safe);
const NODES_MAX = 100_000;

export function text_safe(text: string): boolean {
    return !/undefined|NaN|\[object/.test(text);
}

export function texts_unsafe(element: Element): string[] {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const unsafe: string[] = [];

    for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
        const text = node.textContent ?? '';

        if (!text_safe(text)) {
            unsafe.push(text);
        }
    }

    return unsafe;
}

export const TEXT_ARBITRARY = fc.string({ maxLength: 24 }).filter(text_safe);

const VALUE_ARBITRARY: Arbitrary<unknown> = fc.oneof(
    TEXT_ARBITRARY,
    fc.integer({ max: 100_000, min: -1_000 }),
    fc.boolean(),
    fc.constant(null),
    fc.array(TEXT_ARBITRARY, { maxLength: 3 }),
);

function number_finite_is(value: unknown): boolean {
    if (typeof value !== 'number') return false;
    return Number.isFinite(value);
}

function record_is(value: unknown): boolean {
    if (value === null) return false;
    if (typeof value !== 'object') return false;
    return !Array.isArray(value);
}

function type_matches(value: unknown, name: string): boolean {
    switch (name) {
        case 'array':
            return Array.isArray(value);
        case 'boolean':
            return typeof value === 'boolean';
        case 'integer':
            return Number.isInteger(value);
        case 'null':
            return value === null;
        case 'number':
            return number_finite_is(value);
        case 'object':
            return record_is(value);
        case 'string':
            return typeof value === 'string';
        default:
            throw new Error('the contract names an unknown type: ' + name);
    }
}

function object_errors(
    value: Record<string, unknown>,
    node: Schema,
    path: string,
    stack: StackEntry[],
): string[] {
    const errors: string[] = [];
    const properties = node.properties ?? {};
    const additional = node.additionalProperties ?? {};

    for (const key of node.required ?? []) {
        if (!Object.hasOwn(value, key)) {
            errors.push(path + ': missing ' + key);
        }
    }

    for (const key of Object.keys(value)) {
        const property = properties[key];

        if (property !== undefined) {
            stack.push([value[key], property, path + '.' + key]);
        } else if (additional === false) {
            errors.push(path + ': unexpected ' + key);
        } else if (additional !== true) {
            stack.push([value[key], additional, path + '.' + key]);
        }
    }

    return errors;
}

function node_errors(value: unknown, node: Schema, path: string, stack: StackEntry[]): string[] {
    if (node.type === undefined) return [];

    const allowed = Array.isArray(node.type) ? node.type : [node.type];
    const matched = allowed.some(function(name) { return type_matches(value, name); });

    if (!matched) return [path + ': expected ' + allowed.join('|')];

    if (Array.isArray(value)) {
        value.forEach(function(item, index) {
            stack.push([item, node.items ?? {}, path + '[' + index + ']']);
        });

        return [];
    }

    if (value === null) return [];
    if (typeof value !== 'object') return [];

    return object_errors(value as Record<string, unknown>, node, path, stack);
}

export function schema_errors(value: unknown, schema: Schema): string[] {
    const errors: string[] = [];
    const stack: StackEntry[] = [[value, schema, '$']];

    for (let step = 0; step < NODES_MAX; step++) {
        if (stack.length === 0) break;
        if (errors.length >= ERRORS_MAX) break;

        const entry = stack.pop();

        if (entry === undefined) break;

        const [current, node, path] = entry;

        errors.push(...node_errors(current, node, path, stack));
    }

    return errors;
}

export function contract_errors(entry: ContractEntry, value: unknown): string[] {
    const variants = entry.variants ?? [entry];
    let closest: string[] | null = null;

    for (const variant of variants) {
        const errors = schema_errors(value, variant);

        if (errors.length === 0) return [];

        if (closest !== null) {
            if (errors.length >= closest.length) continue;
        }

        closest = errors;
    }

    return closest ?? [];
}

function schema_children(node: Schema): Schema[] {
    const children: Schema[] = [];

    for (const property of Object.values(node.properties ?? {})) {
        children.push(property);
    }

    if (node.items) {
        children.push(node.items);
    }

    if (node.additionalProperties) {
        if (typeof node.additionalProperties === 'object') {
            children.push(node.additionalProperties);
        }
    }

    return children;
}

function built_get(built: BuiltArbitraries, node: Schema): Arbitrary<unknown> {
    const arbitrary = built.get(node);

    if (arbitrary === undefined) {
        throw new Error('the schema node was not built before its parent');
    }

    return arbitrary;
}

function object_arbitrary(node: Schema, built: BuiltArbitraries): Arbitrary<unknown> {
    const properties = node.properties ?? {};
    const shape: Record<string, Arbitrary<unknown>> = {};

    for (const [key, property] of Object.entries(properties)) {
        shape[key] = built_get(built, property);
    }

    const keys_required = node.required ?? [];
    const record = fc.record(shape, { requiredKeys: keys_required });
    const additional = node.additionalProperties;

    if (!additional) return record;
    if (typeof additional !== 'object') return record;

    const value_arbitrary = built_get(built, additional);
    const extras = fc.dictionary(KEY_ARBITRARY, value_arbitrary, { maxKeys: 3 });

    return fc.tuple(record, extras).map(function([declared, extra]) {
        const merged: Record<string, unknown> = { ...extra };

        for (const key of Object.keys(declared)) {
            merged[key] = declared[key];
        }

        return merged;
    });
}

function type_arbitrary(type: string, node: Schema, built: BuiltArbitraries): Arbitrary<unknown> {
    switch (type) {
        case 'array':
            return fc.array(
                node.items === undefined ? VALUE_ARBITRARY : built_get(built, node.items),
                { maxLength: 4 },
            );
        case 'boolean':
            return fc.boolean();
        case 'integer':
            return fc.integer({ max: 100_000, min: -1_000 });
        case 'null':
            return fc.constant(null);
        case 'number':
            return fc.double({ max: 1_000_000, min: -1_000, noDefaultInfinity: true, noNaN: true });
        case 'object':
            return object_arbitrary(node, built);
        case 'string':
            return TEXT_ARBITRARY;
        default:
            throw new Error('the contract names an unknown type: ' + type);
    }
}

function node_arbitrary(node: Schema, built: BuiltArbitraries): Arbitrary<unknown> {
    if (node.type === undefined) return VALUE_ARBITRARY;

    const types = Array.isArray(node.type) ? node.type : [node.type];
    const options = types.map(function(type) { return type_arbitrary(type, node, built); });

    return fc.oneof(...options);
}

export function schema_arbitrary(root: Schema): Arbitrary<unknown> {
    const order: Schema[] = [];
    const stack: Schema[] = [root];

    for (let step = 0; step < NODES_MAX; step++) {
        if (stack.length === 0) break;

        const node = stack.pop();

        if (node === undefined) break;

        order.push(node);
        stack.push(...schema_children(node));
    }

    const built: BuiltArbitraries = new Map();

    for (const node of order.toReversed()) {
        built.set(node, node_arbitrary(node, built));
    }

    return built_get(built, root);
}

export function contract_arbitrary(entry: ContractEntry): Arbitrary<unknown> {
    const variants = entry.variants ?? [entry];

    return fc.oneof(...variants.map(schema_arbitrary));
}
