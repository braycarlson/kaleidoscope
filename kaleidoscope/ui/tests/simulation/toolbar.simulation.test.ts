import { describe, expect, it } from 'vitest';
import { SOMETIMES_TARGETS, simulation_run } from './engine';
import { seeds_from_environment, step_count_from_environment } from './rng';

const FAULTS_NONE = Object.freeze({ drop: 0, error: 0 });
const FAULTS_SOME = Object.freeze({ drop: 0.12, error: 0.08 });
const STEP_COUNT = step_count_from_environment();
const SWEEP_SEEDS = 8;
const SWEEP_STEP_COUNT = 300;
const TIMEOUT_MS = 120_000;

describe('the toolbar simulation', function() {
    it.each(seeds_from_environment())(
        'holds every invariant on a reliable network with seed %i',
        async function(seed) {
            await simulation_run(seed, STEP_COUNT, FAULTS_NONE);
        },
        TIMEOUT_MS,
    );

    it.each(seeds_from_environment())(
        'holds every invariant on a faulty network with seed %i',
        async function(seed) {
            await simulation_run(seed, STEP_COUNT, FAULTS_SOME);
        },
        TIMEOUT_MS,
    );

    it('reaches every sometimes target across a fixed sweep', async function() {
        const reached: Record<string, number> = {};

        for (let seed = 0; seed < SWEEP_SEEDS; seed++) {
            const counts = await simulation_run(seed, SWEEP_STEP_COUNT, FAULTS_SOME);

            for (const [name, count] of Object.entries(counts)) {
                reached[name] = (reached[name] ?? 0) + count;
            }
        }

        const unreached = SOMETIMES_TARGETS.filter(function(target) { return !reached[target]; });

        expect(unreached).toEqual([]);
    }, TIMEOUT_MS * 4);
});
