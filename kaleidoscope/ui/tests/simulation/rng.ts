export interface Rng {
    chance: (probability: number) => boolean;
    choice: <T>(items: readonly T[]) => T;
    integer: (min: number, max: number) => number;
    next: () => number;
    seed: number;
}

const SEED_COUNT_DEFAULT = 1;
const SEED_COUNT_MAX = 10_000;
const STEP_COUNT_DEFAULT = 300;
const STEP_COUNT_MAX = 100_000;

export function rng_create(seed: number): Rng {
    let state = seed >>> 0;

    function next(): number {
        state = (state + 0x6D2B79F5) >>> 0;

        let mixed = state;

        mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
        mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);

        return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
    }

    function integer(min: number, max: number): number {
        return min + Math.floor(next() * (max - min + 1));
    }

    function choice<T>(items: readonly T[]): T {
        if (items.length === 0) throw new Error('choice needs at least one item');

        const item = items[integer(0, items.length - 1)];

        if (item === undefined) throw new Error('choice drew an index outside the items');

        return item;
    }

    function chance(probability: number): boolean {
        return next() < probability;
    }

    return { chance, choice, integer, next, seed };
}

function integer_within(value: number, maximum: number): boolean {
    if (!Number.isInteger(value)) return false;
    if (value < 0) return false;
    return value <= maximum;
}

function environment_integer(name: string, fallback: number, maximum: number): number {
    const raw = (process.env[name] ?? '').trim();

    if (!raw) return fallback;

    const value = Number(raw);

    if (!integer_within(value, maximum)) {
        throw new Error(
            name + ' must be an integer between 0 and ' + maximum + ', received ' + raw,
        );
    }

    return value;
}

export function seeds_from_environment(): number[] {
    const listed = (process.env['SIMULATION_SEEDS'] ?? '').trim();

    if (listed) {
        return listed.split(',').map(function(part) {
            const seed = Number(part.trim());

            if (!integer_within(seed, Infinity)) {
                throw new Error(
                    'SIMULATION_SEEDS entries must be non-negative integers, received ' + part,
                );
            }

            return seed;
        });
    }

    const start = environment_integer('SIMULATION_SEED_START', 0, 2 ** 31);
    const count = environment_integer('SIMULATION_SEED_COUNT', SEED_COUNT_DEFAULT, SEED_COUNT_MAX);

    return Array.from({ length: count }, function(_, index) { return start + index; });
}

export function step_count_from_environment(): number {
    const step_count = environment_integer(
        'SIMULATION_STEP_COUNT',
        STEP_COUNT_DEFAULT,
        STEP_COUNT_MAX,
    );

    if (step_count < 1) {
        throw new Error('SIMULATION_STEP_COUNT must be at least 1, received ' + step_count);
    }

    return step_count;
}
