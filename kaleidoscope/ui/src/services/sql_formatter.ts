type FormatterFunction = (sql: string) => string;

let formatter_promise: Promise<FormatterFunction> | null = null;
let formatter_cached: FormatterFunction | null = null;

function create_formatter(module: typeof import('sql-formatter')): FormatterFunction {
    function formatter(sql: string): string {
        return module.format(sql, {
            language: 'postgresql',
            keywordCase: 'upper',
            tabWidth: 4,
        });
    }

    return formatter;
}

export function sql_formatter_preload(): Promise<FormatterFunction> {
    if (formatter_promise) return formatter_promise;

    formatter_promise = import('sql-formatter').then(function(module) {
        formatter_cached = create_formatter(module);

        return formatter_cached;
    }).catch(function(error: unknown) {
        formatter_promise = null;

        throw error;
    });

    return formatter_promise;
}

export function sql_formatter_get(): FormatterFunction | null {
    return formatter_cached;
}
