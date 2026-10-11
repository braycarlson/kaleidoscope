const RUNS_DEFAULT = 60;
const RUNS_LIMIT = 100_000;

function runs_valid(runs: number): boolean {
    if (!Number.isInteger(runs)) return false;
    if (runs < 1) return false;
    return runs <= RUNS_LIMIT;
}

export function fuzz_runs(): number {
    const configured = (process.env['FUZZ_CASES'] ?? '').trim();

    if (!configured) return RUNS_DEFAULT;

    const runs = Number(configured);

    if (!runs_valid(runs)) {
        throw new Error(
            'FUZZ_CASES must be an integer between 1 and ' + RUNS_LIMIT
            + ', received ' + configured,
        );
    }

    return runs;
}

export function fuzz_timeout(): number {
    return Math.max(10_000, fuzz_runs() * 25);
}
