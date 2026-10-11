<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { ChevronRight, Trash2 } from 'lucide-vue-next';
import { fetch_native, json_fetch } from '../../services/api';
import { sql_formatter_preload } from '../../services/sql_formatter';
import { use_sort, compare_sort_values } from '../../composables/use_sort';
import { rows_hidden_count, rows_visible } from '../../services/table';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
import RowsMore from '../RowsMore.vue';
import QueryDetail from './QueryDetail.vue';
import SortHeader from './SortHeader.vue';
import type { StackFrame, SortDirection, QuerySortState, TemplateFrame } from '../../types';

interface QueryEntry {
    alias?: string;
    sql: string;
    raw_sql: string | null;
    params: string | null;
    many: boolean;
    rows: number | null;
    stack: StackFrame[];
    templates: TemplateFrame[];
    time: number;
}

interface RequestEntry {
    _key: string;
    duration: number;
    duplicate_count: number;
    is_ajax: boolean;
    method: string;
    path: string;
    queries: QueryEntry[];
    query_count: number;
    query_time: number;
    request_id: string;
    rows_known: boolean;
    status_code: number;
    timestamp: number;
}

type RequestRaw = Omit<RequestEntry, '_key' | 'duplicate_count' | 'rows_known'>;

interface QueryEnriched {
    alias: string;
    duplicate_count: number;
    index: number;
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

interface QueryGroup {
    sql: string;
    occurrences: QueryEnriched[];
    count: number;
    time_total_ms: number;
    time_avg_ms: number;
    time_slowest_ms: number;
    primary: QueryEnriched;
}

interface SimilarGroup {
    count: number;
    example: string;
    total_time: number;
}

interface QueriesPanelData {
    duplicates: Record<string, number>;
    requests: RequestRaw[];
    similar: Record<string, SimilarGroup>;
    summary: { request_count: number; total_queries: number; total_query_time: number };
    track_ajax: boolean;
    track_page: boolean;
}

const QUERY_SORT_COLUMNS: readonly string[] = Object.freeze([
    'alias',
    'duplicate_count',
    'index',
    'many',
    'params',
    'raw_sql',
    'rows',
    'sql',
    'time_ms',
]);

const props = defineProps<{
    data: QueriesPanelData;
}>();

const emit = defineEmits<{
    refresh: [];
}>();

const requests_expanded = reactive<Record<string, boolean>>({});
const groups_expanded = reactive<Record<string, boolean>>({});
const groups_complete = reactive<Record<string, boolean>>({});
const occurrences_complete = reactive<Record<string, boolean>>({});
const track_ajax = ref(props.data.track_ajax);
const track_page = ref(props.data.track_page);
const query_selected = ref<QueryEnriched | null>(null);
const query_selected_index = ref(0);
const query_selected_duplicate_count = ref(0);
const sorts_query = reactive<Record<string, QuerySortState>>({});
const text_filter = ref('');
const text_filter_similar = ref('');

onMounted(function() {
    sql_formatter_preload().catch(function() {
        // preload failed, QueryDetail will fall back to raw SQL
    });
});

watch(function() { return props.data.track_ajax; }, function(value) {
    track_ajax.value = value;
});

watch(function() { return props.data.track_page; }, function(value) {
    track_page.value = value;
});

const count_duplicate = computed(function() {
    let total = 0;

    for (const count of Object.values(props.data.duplicates)) {
        total += count - 1;
    }

    return total;
});

const groups_similar = computed(function() {
    const groups = Object.values(props.data.similar);

    return groups.sort(function(a, b) {
        return b.count - a.count;
    });
});

const groups_similar_filtered = computed(function() {
    const search = text_filter_similar.value.toLowerCase();

    if (!search) return groups_similar.value;

    return groups_similar.value.filter(function(group) {
        return group.example.toLowerCase().includes(search);
    });
});

const query_time_maximum = computed(function() {
    let maximum = 0;

    for (const request of props.data.requests) {
        for (const query of request.queries) {
            const time_ms = query.time * 1000;

            if (time_ms > maximum) {
                maximum = time_ms;
            }
        }
    }

    return maximum || 1;
});

const requests_enriched = computed(function(): RequestEntry[] {
    const duplicates = props.data.duplicates;

    return props.data.requests.map(function(request: RequestRaw, request_index: number) {
        let duplicate_count = 0;
        let rows_known = false;

        for (const query of request.queries) {
            if ((duplicates[query.sql] ?? 0) > 1) {
                duplicate_count++;
            }

            if (query.rows !== null) {
                rows_known = true;
            }
        }

        return {
            ...request,
            _key: request_index + ':' + request.timestamp,
            duplicate_count: duplicate_count,
            rows_known: rows_known,
        };
    });
});

const { sort_column, sort_direction, sorted: requests_sorted, sort_toggle } = use_sort(requests_enriched, 'query_time', 'desc');

const stats_header = computed(function() {
    const items: { label: string; value: string | number }[] = [
        { label: 'Requests', value: props.data.summary.request_count },
        { label: 'Queries', value: props.data.summary.total_queries },
    ];

    if (count_duplicate.value > 0) {
        items.push({ label: 'Duplicates', value: count_duplicate.value });
    }

    if (groups_similar.value.length > 0) {
        items.push({ label: 'Similar Groups', value: groups_similar.value.length });
    }

    items.push({ label: 'Time', value: props.data.summary.total_query_time + ' ms' });

    return items;
});

const requests_filtered = computed(function(): RequestEntry[] {
    const search = text_filter.value.toLowerCase();

    if (!search) return requests_sorted.value;

    return requests_sorted.value.filter(function(request) {
        if (request.path.toLowerCase().includes(search)) return true;
        if (request.method.toLowerCase().includes(search)) return true;

        for (const query of request.queries) {
            if (query.sql.toLowerCase().includes(search)) return true;
        }

        return false;
    });
});

function request_toggle(request_key: string) {
    requests_expanded[request_key] = !requests_expanded[request_key];
}

function group_key(request_key: string, sql: string): string {
    return request_key + ':' + sql;
}

function group_toggle(request_key: string, sql: string) {
    const key = group_key(request_key, sql);
    groups_expanded[key] = !groups_expanded[key];
}

function group_is_expanded(request_key: string, sql: string): boolean {
    return groups_expanded[group_key(request_key, sql)] === true;
}

function groups_of(request_key: string): QueryGroup[] {
    return groups_by_request.value.get(request_key) ?? [];
}

function occurrences_are_complete(request_key: string, sql: string): boolean {
    return occurrences_complete[group_key(request_key, sql)] === true;
}

function occurrences_show(request_key: string, sql: string) {
    occurrences_complete[group_key(request_key, sql)] = true;
}

function width_bar(time_ms: number): number {
    if (!Number.isFinite(time_ms)) {
        throw new RangeError('a bar needs a finite time in ms: ' + time_ms);
    }

    return Math.max(2, Math.min(100, time_ms / query_time_maximum.value * 100));
}

function color_bar(time_ms: number): string {
    if (time_ms < 2) return '#4caf50';
    if (time_ms < 10) return '#ff9800';
    return '#f44336';
}

function rows_text(rows: number | null): string {
    if (rows === null) return '';
    if (!Number.isFinite(rows)) throw new RangeError('a row count must be finite: ' + rows);
    return String(rows);
}

function template_location(query: QueryEnriched): string {
    if (!Array.isArray(query.templates)) {
        throw new TypeError('template frames must be a list: ' + String(query.templates));
    }

    const frame = query.templates[query.templates.length - 1];

    if (frame === undefined) return '';
    return frame.name + ':' + frame.line + ' ' + frame.text;
}

function queries_get(request: RequestEntry): QueryEnriched[] {
    const duplicates = props.data.duplicates;

    const queries: QueryEnriched[] = request.queries.map(function(query, index) {
        return {
            alias: query.alias ?? 'default',
            sql: query.sql,
            raw_sql: query.raw_sql,
            params: query.params,
            many: query.many,
            request_id: request.request_id,
            rows: query.rows,
            stack: query.stack,
            templates: query.templates,
            time_ms: query.time * 1000,
            duplicate_count: duplicates[query.sql] ?? 0,
            index: index,
        };
    });

    const query_sort = sorts_query[request._key];
    const column = query_sort ? query_sort.column : 'time_ms';
    const direction: SortDirection = query_sort ? query_sort.direction : 'desc';

    return queries.slice().sort(function(a, b) {
        const result = compare_sort_values(
            a[column as keyof QueryEnriched],
            b[column as keyof QueryEnriched],
        );

        return direction === 'asc' ? result : -result;
    });
}

function groups_build(request: RequestEntry): QueryGroup[] {
    const queries = queries_get(request);
    const grouped = new Map<string, QueryEnriched[]>();

    for (const query of queries) {
        const occurrences = grouped.get(query.sql);

        if (occurrences === undefined) {
            grouped.set(query.sql, [query]);
        } else {
            occurrences.push(query);
        }
    }

    const groups: QueryGroup[] = Array.from(grouped, function([sql, occurrences]) {
        let total = 0;
        let slowest = 0;

        for (const occurrence of occurrences) {
            total += occurrence.time_ms;

            if (occurrence.time_ms > slowest) {
                slowest = occurrence.time_ms;
            }
        }

        const primary = occurrences.reduce(function(a, b) {
            return a.time_ms >= b.time_ms ? a : b;
        });

        return {
            sql: sql,
            occurrences: occurrences,
            count: occurrences.length,
            time_total_ms: total,
            time_avg_ms: total / occurrences.length,
            time_slowest_ms: slowest,
            primary: primary,
        };
    });

    const query_sort = sorts_query[request._key];
    const column = query_sort ? query_sort.column : 'time_ms';
    const direction: SortDirection = query_sort ? query_sort.direction : 'desc';

    return groups.slice().sort(function(a, b) {
        let value_a: unknown;
        let value_b: unknown;

        if (column === 'time_ms') {
            value_a = a.time_total_ms;
            value_b = b.time_total_ms;
        } else if (column === 'index') {
            value_a = a.primary.index;
            value_b = b.primary.index;
        } else {
            value_a = a.primary[column as keyof QueryEnriched];
            value_b = b.primary[column as keyof QueryEnriched];
        }

        const result = compare_sort_values(value_a, value_b);
        return direction === 'asc' ? result : -result;
    });
}

const groups_by_request = computed(function(): Map<string, QueryGroup[]> {
    const groups = new Map<string, QueryGroup[]>();

    for (const request of requests_filtered.value) {
        if (requests_expanded[request._key]) {
            groups.set(request._key, groups_build(request));
        }
    }

    return groups;
});

function request_queries_format(request: RequestEntry): string {
    const lines: string[] = [];

    lines.push(request.method + ' ' + request.path);
    lines.push(request.query_count + ' queries, ' + request.query_time + ' ms total');
    lines.push('');

    for (const [index, query] of request.queries.entries()) {
        const time_ms = (query.time * 1000).toFixed(1);

        lines.push((index + 1) + '. (' + time_ms + ' ms) ' + query.sql);
    }

    return lines.join('\n');
}

function query_sort_toggle(request_key: string, column: string) {
    if (!QUERY_SORT_COLUMNS.includes(column)) {
        throw new RangeError('queries cannot be sorted by ' + column);
    }

    const query_sort = sorts_query[request_key];

    if (!query_sort) {
        sorts_query[request_key] = { column: column, direction: 'asc' };

        return;
    }

    if (query_sort.column === column) {
        sorts_query[request_key] = { column: column, direction: query_sort.direction === 'asc' ? 'desc' : 'asc' };
    } else {
        sorts_query[request_key] = { column: column, direction: 'asc' };
    }
}

function query_sort_column(request_key: string): string {
    const query_sort = sorts_query[request_key];
    return query_sort ? query_sort.column : 'time_ms';
}

function query_sort_direction(request_key: string): SortDirection {
    const query_sort = sorts_query[request_key];
    return query_sort ? query_sort.direction : 'desc';
}

function query_open(query: QueryEnriched, index: number) {
    query_selected.value = query;
    query_selected_index.value = index;
    query_selected_duplicate_count.value = query.duplicate_count;
}

function query_close() {
    query_selected.value = null;
}

function clear() {
    void fetch_native('/__kaleidoscope__/panels/queries/action/clear/').catch(function() {
        return undefined;
    }).then(function() {
        emit('refresh');
    });
}

function track_ajax_toggle() {
    const enabled = !track_ajax.value;
    const action = enabled ? 'track-ajax-on' : 'track-ajax-off';

    json_fetch('/__kaleidoscope__/panels/queries/action/' + action + '/').then(function() {
        track_ajax.value = enabled;
    }).catch(function() {
        emit('refresh');
    });
}

function track_page_toggle() {
    const enabled = !track_page.value;
    const action = enabled ? 'track-page-on' : 'track-page-off';

    json_fetch('/__kaleidoscope__/panels/queries/action/' + action + '/').then(function() {
        track_page.value = enabled;
    }).catch(function() {
        emit('refresh');
    });
}
</script>

<template>
    <div>
        <QueryDetail
            v-if="query_selected"
            :query="query_selected"
            :index="query_selected_index"
            :duplicate_count="query_selected_duplicate_count"
            @close="query_close"
        />

        <PanelHeader :stats="stats_header" />

        <div class="flex items-center gap-3 sm:gap-6 pb-4 mb-5 border-b border-white/6 flex-wrap">
            <span class="opacity-40 text-[13px]">Track:</span>
            <div class="flex items-center gap-2 cursor-pointer" @click="track_page_toggle">
                <div class="relative w-7 h-4 rounded-full transition-colors" :class="track_page ? 'bg-blue-600' : 'bg-white/10'">
                    <div class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform" :class="{ 'translate-x-3': track_page }" />
                </div>
                <span class="text-[13px]" :class="track_page ? '' : 'opacity-40'">Page</span>
            </div>
            <div class="flex items-center gap-2 cursor-pointer" @click="track_ajax_toggle">
                <div class="relative w-7 h-4 rounded-full transition-colors" :class="track_ajax ? 'bg-purple-600' : 'bg-white/10'">
                    <div class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform" :class="{ 'translate-x-3': track_ajax }" />
                </div>
                <span class="text-[13px]" :class="track_ajax ? '' : 'opacity-40'">AJAX</span>
            </div>
        </div>

        <CollapsibleSection
            v-if="requests_sorted.length"
            title="Queries"
            :count="data.summary.total_queries"
            :value_copy="data.requests"
        >
            <template #actions>
                <button
                    type="button"
                    aria-label="Clear the recorded requests"
                    title="Clear the recorded requests"
                    class="ml-auto text-red-500 hover:text-red-400"
                    @click.stop="clear"
                >
                    <Trash2 :size="13" />
                </button>
            </template>

            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter" placeholder="Filter..." />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse table-fixed min-w-[500px]">
                    <thead>
                        <tr>
                            <th class="w-6 px-1 sm:px-2.5 py-2 text-left text-xs font-semibold opacity-40" />
                            <SortHeader column="is_ajax" :sort_column="sort_column" :sort_direction="sort_direction" label="Type" class="w-16!" @sort="sort_toggle" />
                            <SortHeader column="method" :sort_column="sort_column" :sort_direction="sort_direction" label="Method" class="w-16! sm:w-20!" @sort="sort_toggle" />
                            <SortHeader column="path" :sort_column="sort_column" :sort_direction="sort_direction" label="Path" @sort="sort_toggle" />
                            <SortHeader column="status_code" :sort_column="sort_column" :sort_direction="sort_direction" label="Status" class="w-16! hidden sm:table-cell" @sort="sort_toggle" />
                            <SortHeader column="query_count" :sort_column="sort_column" :sort_direction="sort_direction" label="Queries" class="w-[70px]!" @sort="sort_toggle" />
                            <SortHeader column="query_time" :sort_column="sort_column" :sort_direction="sort_direction" label="Time" class="w-20! sm:w-24!" @sort="sort_toggle" />
                            <SortHeader column="duration" :sort_column="sort_column" :sort_direction="sort_direction" label="Total" class="w-24! hidden sm:table-cell" @sort="sort_toggle" />
                            <SortHeader column="duplicate_count" :sort_column="sort_column" :sort_direction="sort_direction" label="Duplicates" class="w-24! hidden sm:table-cell" @sort="sort_toggle" />
                        </tr>
                    </thead>
                    <tbody>
                        <template v-for="request in requests_filtered" :key="request._key">
                            <tr class="cursor-pointer hover:bg-white/3" @click="request_toggle(request._key)">
                                <td class="w-6 px-1 sm:px-2.5 py-2.5 border-b border-white/4">
                                    <ChevronRight :size="12" class="inline-block opacity-30 transition-transform" :class="{ 'rotate-90': requests_expanded[request._key] }" />
                                </td>
                                <td class="w-16 px-2 py-2.5 border-b border-white/4">
                                    <span class="inline-block px-1.5 py-px rounded-sm text-[11px] font-bold" :class="request.is_ajax ? 'bg-purple-700 text-white' : 'bg-blue-600 text-white'">{{ request.is_ajax ? 'AJAX' : 'PAGE' }}</span>
                                </td>
                                <td class="w-16 sm:w-20 px-2 py-2.5 border-b border-white/4 font-semibold">{{ request.method }}</td>
                                <td class="px-2 py-2.5 border-b border-white/4 opacity-70 overflow-hidden text-ellipsis whitespace-nowrap max-w-0" :title="request.path">{{ request.path }}</td>
                                <td class="w-16 px-2 py-2.5 border-b border-white/4 font-semibold hidden sm:table-cell" :class="request.status_code >= 400 ? 'text-red-500' : ''">{{ request.status_code }}</td>
                                <td class="w-[70px] px-2 py-2.5 border-b border-white/4" :class="request.query_count > 10 ? 'text-orange-500 font-semibold' : ''">{{ request.query_count }}</td>
                                <td class="w-20 sm:w-24 px-2 py-2.5 border-b border-white/4 font-mono whitespace-nowrap">{{ request.query_time }} ms</td>
                                <td class="w-24 px-2 py-2.5 border-b border-white/4 font-mono whitespace-nowrap hidden sm:table-cell">{{ request.duration }} ms</td>
                                <td class="w-24 px-2 py-2.5 border-b border-white/4 hidden sm:table-cell" :class="request.duplicate_count > 10 ? 'text-orange-500 font-semibold' : ''">{{ request.duplicate_count || '' }}</td>
                            </tr>
                            <tr v-if="requests_expanded[request._key]">
                                <td colspan="9" class="p-0! px-1! sm:px-2.5! pb-4! border-b border-white/6">
                                    <div class="overflow-x-auto">
                                        <table class="w-full border-collapse min-w-[350px] sm:min-w-[500px]">
                                            <thead>
                                                <tr>
                                                    <th class="px-2 py-1.5 text-left text-[11px] font-semibold">
                                                        <div class="flex items-center justify-between">
                                                            <span>Queries ({{ request.query_count }})</span>
                                                            <CopyButton :value="request_queries_format(request)" :size="11" />
                                                        </div>
                                                    </th>
                                                </tr>
                                            </thead>
                                        </table>
                                        <table class="w-full border-collapse table-fixed min-w-[350px] sm:min-w-[500px]">
                                            <thead>
                                                <tr>
                                                    <th class="w-5 px-2 py-1.5 hidden sm:table-cell" />
                                                    <th class="w-[120px] px-2 py-1.5 text-left text-[11px] font-semibold opacity-40 hidden sm:table-cell">Bar</th>
                                                    <SortHeader :column="'time_ms'" :sort_column="query_sort_column(request._key)" :sort_direction="query_sort_direction(request._key)" label="Time" class="w-[90px]! sm:w-[110px]!" @sort="query_sort_toggle(request._key, $event)" />
                                                    <th class="w-[60px] px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">Count</th>
                                                    <SortHeader v-if="request.rows_known" :column="'rows'" :sort_column="query_sort_column(request._key)" :sort_direction="query_sort_direction(request._key)" label="Rows" class="w-[70px]! hidden sm:table-cell" @sort="query_sort_toggle(request._key, $event)" />
                                                    <th class="px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">SQL</th>
                                                    <th class="w-8 px-2 py-1.5" />
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <template v-for="group in rows_visible(groups_of(request._key), groups_complete[request._key] === true)" :key="group.sql">
                                                    <tr class="hover:bg-white/3">
                                                        <td
                                                            class="w-5 px-2 py-1.5 border-t border-white/4 align-middle hidden sm:table-cell"
                                                            :class="group.count > 1 ? 'cursor-pointer' : ''"
                                                            @click.stop="group.count > 1 ? group_toggle(request._key, group.sql) : null"
                                                        >
                                                            <ChevronRight
                                                                v-if="group.count > 1"
                                                                :size="12"
                                                                class="opacity-40 transition-transform"
                                                                :class="group_is_expanded(request._key, group.sql) ? 'rotate-90' : ''"
                                                            />
                                                        </td>
                                                        <td
                                                            class="w-[120px] px-2 py-1.5 border-t border-white/4 align-middle hidden sm:table-cell cursor-pointer"
                                                            @click.stop="query_open(group.primary, group.primary.index)"
                                                        >
                                                            <div class="h-2 rounded-full bg-white/6 overflow-hidden">
                                                                <div class="h-full rounded-full" :style="{ width: width_bar(group.time_total_ms) + '%', backgroundColor: color_bar(group.time_slowest_ms) }" />
                                                            </div>
                                                        </td>
                                                        <td
                                                            class="w-[90px] sm:w-[110px] px-2 py-1.5 border-t border-white/4 align-top cursor-pointer"
                                                            :class="[group.time_total_ms >= 10 ? 'text-orange-500 font-semibold' : '']"
                                                            :title="group.count > 1 ? 'Total ' + group.time_total_ms.toFixed(1) + ' ms, slowest ' + group.time_slowest_ms.toFixed(1) + ' ms, avg ' + group.time_avg_ms.toFixed(1) + ' ms' : ''"
                                                            @click.stop="query_open(group.primary, group.primary.index)"
                                                        >
                                                            {{ group.time_total_ms.toFixed(1) }} ms
                                                        </td>
                                                        <td class="w-[60px] px-2 py-1.5 border-t border-white/4">
                                                            <span
                                                                v-if="group.count > 1"
                                                                class="inline-block bg-orange-600/80 text-white px-1.5 py-px rounded-sm text-[11px] font-bold cursor-pointer"
                                                                @click.stop="group_toggle(request._key, group.sql)"
                                                            >×{{ group.count }}</span>
                                                        </td>
                                                        <td v-if="request.rows_known" data-ks="query-rows" class="w-[70px] px-2 py-1.5 border-t border-white/4 align-top text-[12px] hidden sm:table-cell">{{ rows_text(group.primary.rows) }}</td>
                                                        <td
                                                            class="px-2 py-1.5 border-t border-white/4 align-top max-w-0 cursor-pointer"
                                                            @click.stop="query_open(group.primary, group.primary.index)"
                                                        >
                                                            <span class="font-mono text-xs leading-relaxed whitespace-nowrap overflow-hidden text-ellipsis block">{{ group.sql }}</span>
                                                            <div
                                                                v-if="template_location(group.primary)"
                                                                data-ks="query-template"
                                                                class="font-mono text-[11px] leading-relaxed opacity-50 whitespace-nowrap overflow-hidden text-ellipsis"
                                                                :title="template_location(group.primary)"
                                                            >
                                                                {{ template_location(group.primary) }}
                                                            </div>
                                                        </td>
                                                        <td
                                                            class="w-8 px-2 py-1.5 border-t border-white/4 cursor-pointer"
                                                            @click.stop="query_open(group.primary, group.primary.index)"
                                                        >
                                                            <ChevronRight :size="14" class="inline-block text-purple-400 opacity-60 hover:opacity-100" />
                                                        </td>
                                                    </tr>
                                                    <template v-if="group.count > 1 && group_is_expanded(request._key, group.sql)">
                                                        <tr
                                                            v-for="occurrence in rows_visible(group.occurrences, occurrences_are_complete(request._key, group.sql))"
                                                            :key="occurrence.index"
                                                            class="cursor-pointer hover:bg-white/3 bg-white/1.5"
                                                            @click.stop="query_open(occurrence, occurrence.index)"
                                                        >
                                                            <td class="w-5 px-2 py-1 border-t border-white/3 hidden sm:table-cell" />
                                                            <td class="w-[120px] px-2 py-1 border-t border-white/3 align-middle hidden sm:table-cell">
                                                                <div class="h-1.5 rounded-full bg-white/6 overflow-hidden">
                                                                    <div class="h-full rounded-full" :style="{ width: width_bar(occurrence.time_ms) + '%', backgroundColor: color_bar(occurrence.time_ms) }" />
                                                                </div>
                                                            </td>
                                                            <td class="w-[90px] sm:w-[110px] px-2 py-1 border-t border-white/3 align-top text-[12px]" :class="[occurrence.time_ms >= 10 ? 'text-orange-500' : 'opacity-70']">{{ occurrence.time_ms.toFixed(1) }} ms</td>
                                                            <td class="w-[60px] px-2 py-1 border-t border-white/3" />
                                                            <td v-if="request.rows_known" class="w-[70px] px-2 py-1 border-t border-white/3 align-top text-[11px] opacity-70 hidden sm:table-cell">{{ rows_text(occurrence.rows) }}</td>
                                                            <td class="px-2 py-1 border-t border-white/3 align-top max-w-0 opacity-60">
                                                                <span class="font-mono text-[11px] leading-relaxed whitespace-nowrap overflow-hidden text-ellipsis block">{{ occurrence.sql }}</span>
                                                            </td>
                                                            <td class="w-8 px-2 py-1 border-t border-white/3">
                                                                <ChevronRight :size="12" class="inline-block text-purple-400 opacity-40 hover:opacity-100" />
                                                            </td>
                                                        </tr>
                                                        <RowsMore
                                                            v-if="rows_hidden_count(group.occurrences, occurrences_are_complete(request._key, group.sql)) > 0"
                                                            :columns="request.rows_known ? 7 : 6"
                                                            :hidden_count="rows_hidden_count(group.occurrences, occurrences_are_complete(request._key, group.sql))"
                                                            @more="occurrences_show(request._key, group.sql)"
                                                        />
                                                    </template>
                                                </template>
                                                <RowsMore
                                                    v-if="rows_hidden_count(groups_of(request._key), groups_complete[request._key] === true) > 0"
                                                    :columns="request.rows_known ? 7 : 6"
                                                    :hidden_count="rows_hidden_count(groups_of(request._key), groups_complete[request._key] === true)"
                                                    @more="groups_complete[request._key] = true"
                                                />
                                            </tbody>
                                        </table>
                                    </div>
                                </td>
                            </tr>
                        </template>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>
        <div v-else-if="!requests_sorted.length" class="py-10 text-center opacity-30 italic">No requests captured</div>

        <CollapsibleSection
            v-if="groups_similar.length"
            :title="'Similar Queries (N+1 Detection): ' + groups_similar.length + ' groups'"
            :value_copy="groups_similar"
        >
            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter_similar" placeholder="Filter..." />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[350px]">
                    <thead>
                        <tr>
                            <th class="w-[60px] px-2 py-1.5 text-left text-xs font-semibold opacity-40">Count</th>
                            <th class="w-[80px] px-2 py-1.5 text-left text-xs font-semibold opacity-40">Time</th>
                            <th class="px-2 py-1.5 text-left text-xs font-semibold opacity-40">Query Pattern</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="(group, i) in groups_similar_filtered" :key="i" class="hover:bg-white/2">
                            <td class="w-[60px] px-2 py-1.5 text-[13px] border-t border-white/4" :class="group.count > 5 ? 'text-orange-500 font-semibold' : ''">{{ group.count }}</td>
                            <td class="w-[80px] px-2 py-1.5 text-[13px] border-t border-white/4">{{ group.total_time.toFixed(2) }} ms</td>
                            <td class="px-2 py-1.5 border-t border-white/4">
                                <div class="overflow-hidden max-h-[22px]">
                                    <span class="font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{{ group.example }}</span>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>
    </div>
</template>
