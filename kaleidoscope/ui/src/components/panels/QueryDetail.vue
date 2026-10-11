<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { X } from 'lucide-vue-next';
import CollapsibleSection from '../CollapsibleSection.vue';
import PanelHeader from '../PanelHeader.vue';
import PrismCode from './PrismCode.vue';
import { fetch_native } from '../../services/api';
import { sql_formatter_get } from '../../services/sql_formatter';
import type { StackFrame, TemplateFrame } from '../../types';

interface QueryData {
    alias?: string;
    duplicate_count: number;
    many: boolean;
    params: string | null;
    raw_sql: string | null;
    request_id: string;
    rows: number | null;
    sql: string;
    stack: StackFrame[];
    templates: TemplateFrame[];
    time_ms: number;
}

interface ExplainAnswer {
    command?: unknown;
    error?: unknown;
    plan?: unknown;
}

const props = defineProps<{
    query: QueryData;
    index: number;
    duplicate_count?: number;
}>();

const emit = defineEmits<{
    close: [];
}>();

const SQL_FORMAT_LENGTH_MAX = 20_000;
const STATEMENT_EXPLAINABLE = /^[\s(]*(select|with)\b/i;

const explain_command = ref('');
const explain_error = ref('');
const explain_loading = ref(false);
const explain_plan = ref('');

function try_format(sql: string): string {
    if (typeof sql !== 'string') {
        throw new TypeError('the sql to format must be text: ' + String(sql));
    }

    const formatter = sql_formatter_get();

    if (!formatter) return sql;
    if (sql.length > SQL_FORMAT_LENGTH_MAX) return sql;

    try {
        return formatter(sql);
    } catch {
        return sql;
    }
}

const sql_formatted = computed(function() {
    return try_format(props.query.sql);
});

const raw_sql_formatted = computed(function() {
    return props.query.raw_sql ? try_format(props.query.raw_sql) : '';
});

const query_number = computed(function(): number {
    if (!Number.isInteger(props.index)) {
        throw new TypeError('a query index must be an integer: ' + props.index);
    }

    if (props.index < 0) throw new RangeError('a query index must not be negative: ' + props.index);
    return props.index + 1;
});

const stats_header = computed(function() {
    if (!Number.isFinite(props.query.time_ms)) {
        throw new RangeError('a query time must be a finite number: ' + props.query.time_ms);
    }

    const items: { label: string; value: string | number }[] = [
        { label: 'Duration', value: props.query.time_ms.toFixed(2) + ' ms' },
    ];

    const rows = props.query.rows;

    if (typeof rows === 'number') {
        if (!Number.isFinite(rows)) throw new RangeError('a row count must be finite: ' + rows);
        items.push({ label: 'Rows', value: rows });
    }

    if (props.query.alias && props.query.alias !== 'default') {
        items.push({ label: 'Database', value: props.query.alias });
    }

    if (props.query.many) {
        items.push({ label: 'Type', value: 'executemany' });
    }

    if ((props.duplicate_count ?? 0) > 1) {
        items.push({ label: 'Duplicates', value: props.duplicate_count ?? 0 });
    }

    return items;
});

const explainable = computed(function(): boolean {
    if (props.query.many) return false;
    return STATEMENT_EXPLAINABLE.test(props.query.raw_sql ?? props.query.sql);
});

const templates = computed(function(): TemplateFrame[] {
    const frames = props.query.templates;

    if (!Array.isArray(frames)) {
        throw new TypeError('template frames must be a list: ' + String(frames));
    }

    return frames;
});

watch(function() { return props.query; }, function() {
    explain_command.value = '';
    explain_error.value = '';
    explain_loading.value = false;
    explain_plan.value = '';
});

function explain_answer_apply(status: number, body: ExplainAnswer) {
    explain_loading.value = false;

    if (typeof body.plan === 'string') {
        explain_command.value = typeof body.command === 'string' ? body.command : '';
        explain_plan.value = body.plan;

        return;
    }

    explain_error.value = typeof body.error === 'string' ? body.error : 'HTTP ' + status;
}

function explain_run() {
    const query_requested = props.query;
    const request_id = query_requested.request_id;

    if (typeof request_id !== 'string') {
        throw new TypeError('a request id must be text: ' + String(request_id));
    }

    explain_error.value = '';
    explain_loading.value = true;

    const url = '/__kaleidoscope__/panels/queries/action/explain/'
        + '?request=' + encodeURIComponent(request_id)
        + '&query=' + props.index;

    fetch_native(url).then(function(response) {
        return response.json().catch(function() { return {}; }).then(function(body: ExplainAnswer) {
            if (props.query !== query_requested) return;

            explain_answer_apply(response.status, body);
        });
    }).catch(function(error: unknown) {
        if (props.query !== query_requested) return;

        explain_loading.value = false;
        explain_error.value = String(error);
    });
}
</script>

<template>
    <div class="fixed inset-0 z-1000001 flex items-stretch justify-end">
        <div class="flex-1 bg-ks-overlay hidden sm:block" @click="emit('close')" />
        <div class="w-full sm:w-[700px] sm:max-w-[80vw] bg-ks-panel border-l border-ks flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-3 sm:px-5 py-3 border-b border-ks-subtle bg-ks-header shrink-0">
                <span class="font-semibold text-sm">Query #{{ query_number }}</span>
                <div class="flex items-center shrink-0">
                    <button type="button" aria-label="Close the query" class="text-ks-muted hover:text-ks" @click="emit('close')">
                        <X :size="18" />
                    </button>
                </div>
            </div>
            <div class="flex-1 overflow-y-auto p-3 sm:p-5">
                <PanelHeader :stats="stats_header" />

                <CollapsibleSection title="SQL" :value_copy="query.sql">
                    <PrismCode :code="sql_formatted" language="sql" block />
                </CollapsibleSection>

                <CollapsibleSection v-if="query.raw_sql" title="Raw SQL" :value_copy="query.raw_sql">
                    <PrismCode :code="raw_sql_formatted" language="sql" block />
                </CollapsibleSection>

                <CollapsibleSection v-if="query.params" title="Parameters" :value_copy="query.params">
                    <PrismCode :code="query.params" language="python" block />
                </CollapsibleSection>

                <CollapsibleSection v-if="explainable" title="EXPLAIN" :value_copy="explain_plan || undefined">
                    <div v-if="explain_plan">
                        <div v-if="explain_command" class="font-mono text-[11px] text-ks-faint mb-2">{{ explain_command }}</div>
                        <PrismCode :code="explain_plan" language="plain" block />
                    </div>
                    <div v-else class="flex items-center gap-3 flex-wrap">
                        <button
                            type="button"
                            data-ks="explain"
                            class="text-[12px] text-purple-400 hover:text-purple-300 disabled:opacity-40"
                            :disabled="explain_loading"
                            @click="explain_run"
                        >
                            {{ explain_loading ? 'Explaining...' : 'Run EXPLAIN' }}
                        </button>
                        <span v-if="explain_error" class="text-[12px] text-red-400 break-all">Error: {{ explain_error }}</span>
                    </div>
                </CollapsibleSection>

                <CollapsibleSection v-if="templates.length" title="Template" :value_copy="templates">
                    <div class="rounded-sm border border-ks-section overflow-hidden bg-ks-code">
                        <div
                            v-for="(frame, i) in templates"
                            :key="i"
                            class="px-3 py-2 border-b border-ks-row last:border-0 hover:bg-ks-hover"
                        >
                            <div class="font-mono text-[12px] text-blue-400 overflow-hidden text-ellipsis whitespace-nowrap" :title="frame.name">{{ frame.name }}:{{ frame.line }}</div>
                            <div v-if="frame.text" class="font-mono text-[11px] text-ks-muted mt-0.5 pl-2 border-l-2 border-ks-section break-all">{{ frame.text }}</div>
                        </div>
                    </div>
                </CollapsibleSection>

                <CollapsibleSection v-if="query.stack && query.stack.length" title="Stack Trace" :value_copy="query.stack">
                    <div class="rounded-sm border border-ks-section overflow-hidden bg-ks-code">
                        <div
                            v-for="(frame, i) in query.stack"
                            :key="i"
                            class="px-3 py-2 border-b border-ks-row last:border-0 hover:bg-ks-hover"
                        >
                            <div class="flex items-baseline gap-2">
                                <span class="font-mono text-[12px] text-blue-400 shrink-0">{{ frame.function }}</span>
                                <span class="font-mono text-[11px] text-ks-faint overflow-hidden text-ellipsis whitespace-nowrap" :title="frame.file">{{ frame.file }}:{{ frame.line }}</span>
                            </div>
                            <div v-if="frame.text" class="font-mono text-[11px] text-ks-muted mt-0.5 pl-2 border-l-2 border-ks-section">{{ frame.text }}</div>
                        </div>
                    </div>
                </CollapsibleSection>
            </div>
        </div>
    </div>
</template>
