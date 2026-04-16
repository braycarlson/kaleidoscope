type FormatterFunction = (sql: string) => string;

let formatter_promise: Promise<FormatterFunction> | null = null;
let formatter_cached: FormatterFunction | null = null;

function create_formatter(module: typeof import('sql-formatter')): FormatterFunction {
    return function(sql: string) {
        return module.format(sql, {
            language: 'postgresql',
            keywordCase: 'upper',
            tabWidth: 4,
        });
    };
}

export function sql_formatter_preload(): Promise<FormatterFunction> {
    if (formatter_promise) return formatter_promise;

    formatter_promise = import('sql-formatter').then(function(module) {
        formatter_cached = create_formatter(module);
        return formatter_cached;
    }).catch(function(err) {
        formatter_promise = null;
        throw err;
    });

    return formatter_promise;
}

export function sql_formatter_get(): FormatterFunction | null {
    return formatter_cached;
}
