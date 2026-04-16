<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { ChevronRight, Trash2 } from 'lucide-vue-next';
import { fetch_native, json_fetch } from '../../services/api';
import { use_sort, compare_sort_values } from '../../composables/use_sort';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import FilterInput from '../FilterInput.vue';
import QueryDetail from './QueryDetail.vue';
import SortHeader from './SortHeader.vue';
import type { StackFrame, SortDirection, QuerySortState } from '../../types';

interface QueryEntry {
    sql: string;
    raw_sql: string | null;
    params: string | null;
    many: boolean;
    stack: StackFrame[];
    time: number;
}

interface RequestEntry {
    duration: number;
    duplicate_count: number;
    is_ajax: boolean;
    method: string;
    path: string;
    queries: QueryEntry[];
    query_count: number;
    query_time: number;
    status_code: number;
    timestamp: number;
}

interface QueryEnriched {
    duplicate_count: number;
    index: number;
    many: boolean;
    params: string | null;
    raw_sql: string | null;
    sql: string;
    stack: StackFrame[];
    time_ms: number;
}

interface SimilarGroup {
    count: number;
    example: string;
    total_time: number;
}

interface QueriesPanelData {
    duplicates: Record<string, number>;
    requests: RequestEntry[];
    similar: Record<string, SimilarGroup>;
    summary: { request_count: number; total_queries: number; total_query_time: number };
    track_ajax: boolean;
    track_page: boolean;
}

const props = defineProps<{
    data: QueriesPanelData;
}>();

const emit = defineEmits<{
    refresh: [];
}>();

const requests_expanded = reactive<Record<number, boolean>>({});
const track_ajax = ref(props.data.track_ajax !== false);
const track_page = ref(props.data.track_page !== false);
const query_selected = ref<QueryEnriched | null>(null);
const query_selected_index = ref(0);
const query_selected_duplicate_count = ref(0);
const sorts_query = reactive<Record<number, QuerySortState>>({});
const text_filter = ref('');

const count_duplicate = computed(function() {
    let total = 0;
    const duplicates: Record<string, number> = props.data.duplicates || {};

    for (const key of Object.keys(duplicates)) {
        total += duplicates[key] - 1;
    }

    return total;
});

const groups_similar = computed(function(): SimilarGroup[] {
    const groups: SimilarGroup[] = [];
    const similar: Record<string, SimilarGroup> = props.data.similar || {};

    for (const key of Object.keys(similar)) {
        groups.push(similar[key]);
    }

    return groups.sort(function(a, b) {
        return b.count - a.count;
    });
});

const query_time_maximum = computed(function() {
    let maximum = 0;

    for (let index = 0; index < props.data.requests.length; index++) {
        for (let query_index = 0; query_index < props.data.requests[index].queries.length; query_index++) {
            const time_ms = props.data.requests[index].queries[query_index].time * 1000;
            if (time_ms > maximum) maximum = time_ms;
        }
    }

    return maximum || 1;
});

const requests_enriched = computed(function(): RequestEntry[] {
    const duplicates: Record<string, number> = props.data.duplicates || {};

    return props.data.requests.map(function(request: RequestEntry) {
        let duplicate_count = 0;

        for (let index = 0; index < request.queries.length; index++) {
            if ((duplicates[request.queries[index].sql] || 0) > 1) duplicate_count++;
        }

        return { ...request, duplicate_count: duplicate_count };
    });
});

const { sort_column, sort_direction, sorted: requests_sorted, sort_toggle } = use_sort(requests_enriched, 'query_time', 'desc');

const requests_filtered = computed(function(): RequestEntry[] {
    const search = text_filter.value.toLowerCase();

    if (!search) return requests_sorted.value;

    return requests_sorted.value.filter(function(request) {
        if (request.path.toLowerCase().includes(search)) return true;
        if (request.method.toLowerCase().includes(search)) return true;

        for (let index = 0; index < request.queries.length; index++) {
            if (request.queries[index].sql.toLowerCase().includes(search)) return true;
        }

        return false;
    });
});

function request_toggle(index: number) {
    requests_expanded[index] = !requests_expanded[index];
}

function width_bar(time_ms: number): number {
    return Math.max(2, Math.min(100, time_ms / query_time_maximum.value * 100));
}

function color_bar(time_ms: number): string {
    if (time_ms < 2) return '#4caf50';
    if (time_ms < 10) return '#ff9800';
    return '#f44336';
}

function queries_get(request: RequestEntry, request_index: number): QueryEnriched[] {
    const duplicates: Record<string, number> = props.data.duplicates || {};

    const queries: QueryEnriched[] = request.queries.map(function(query, index) {
        return {
            sql: query.sql,
            raw_sql: query.raw_sql || null,
            params: query.params || null,
            many: query.many || false,
            stack: query.stack || [],
            time_ms: query.time * 1000,
            duplicate_count: duplicates[query.sql] || 0,
            index: index,
        };
    });

    const query_sort = sorts_query[request_index];
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

function request_queries_format(request: RequestEntry): string {
    const lines: string[] = [];

    lines.push(request.method + ' ' + request.path);
    lines.push(request.query_count + ' queries, ' + request.query_time + ' ms total');
    lines.push('');

    for (let index = 0; index < request.queries.length; index++) {
        const query = request.queries[index];
        const time_ms = (query.time * 1000).toFixed(1);
        lines.push((index + 1) + '. (' + time_ms + ' ms) ' + query.sql);
    }

    return lines.join('\n');
}

function query_sort_toggle(request_index: number, column: string) {
    const query_sort = sorts_query[request_index];

    if (!query_sort) {
        sorts_query[request_index] = { column: column, direction: 'asc' };
        return;
    }

    if (query_sort.column === column) {
        sorts_query[request_index] = { column: column, direction: query_sort.direction === 'asc' ? 'desc' : 'asc' };
    } else {
        sorts_query[request_index] = { column: column, direction: 'asc' };
    }
}

function query_sort_column(request_index: number): string {
    const query_sort = sorts_query[request_index];
    return query_sort ? query_sort.column : 'time_ms';
}

function query_sort_direction(request_index: number): SortDirection {
    const query_sort = sorts_query[request_index];
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
    fetch_native('/__kaleidoscope__/panels/queries/action/clear/').then(function() {
        emit('refresh');
    });
}

function track_ajax_toggle() {
    const action = track_ajax.value ? 'track-ajax-off' : 'track-ajax-on';
    json_fetch('/__kaleidoscope__/panels/queries/action/' + action + '/').then(function() {
        track_ajax.value = !track_ajax.value;
    });
}

function track_page_toggle() {
    const action = track_page.value ? 'track-page-off' : 'track-page-on';
    json_fetch('/__kaleidoscope__/panels/queries/action/' + action + '/').then(function() {
        track_page.value = !track_page.value;
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

        <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-5 border-b border-white/[0.08]">
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Requests</span>
                <span class="font-semibold text-[15px]">{{ data.summary.request_count }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Queries</span>
                <span class="font-semibold text-[15px]">{{ data.summary.total_queries }}</span>
            </div>
            <div v-if="count_duplicate > 0" class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Duplicates</span>
                <span class="font-semibold text-[15px] text-orange-500">{{ count_duplicate }}</span>
            </div>
            <div v-if="groups_similar.length > 0" class="flex items-center gap-2 hidden sm:flex">
                <span class="opacity-40 text-[13px]">Similar Groups</span>
                <span class="font-semibold text-[15px] text-orange-500">{{ groups_similar.length }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Time</span>
                <span class="font-semibold text-[15px]">{{ data.summary.total_query_time }} ms</span>
            </div>
        </div>

        <div class="flex items-center gap-3 sm:gap-6 pb-4 mb-5 border-b border-white/[0.06] flex-wrap">
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
                <button class="ml-auto text-red-500 hover:text-red-400" @click.stop="clear">
                    <Trash2 :size="13" />
                </button>
            </template>

            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter" placeholder="Filter by path or SQL..." />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse table-fixed min-w-[500px]">
                    <thead>
                        <tr>
                            <th class="w-6 px-1 sm:px-2.5 py-2 text-left text-xs font-semibold opacity-40" />
                            <SortHeader column="is_ajax" :sort_column="sort_column" :sort_direction="sort_direction" label="Type" class="!w-16" @sort="sort_toggle" />
                            <SortHeader column="method" :sort_column="sort_column" :sort_direction="sort_direction" label="Method" class="!w-16 sm:!w-20" @sort="sort_toggle" />
                            <SortHeader column="path" :sort_column="sort_column" :sort_direction="sort_direction" label="Path" @sort="sort_toggle" />
                            <SortHeader column="status_code" :sort_column="sort_column" :sort_direction="sort_direction" label="Status" class="!w-16 hidden sm:table-cell" @sort="sort_toggle" />
                            <SortHeader column="query_count" :sort_column="sort_column" :sort_direction="sort_direction" label="Queries" class="!w-[70px]" @sort="sort_toggle" />
                            <SortHeader column="query_time" :sort_column="sort_column" :sort_direction="sort_direction" label="Time" class="!w-20 sm:!w-24" @sort="sort_toggle" />
                            <SortHeader column="duration" :sort_column="sort_column" :sort_direction="sort_direction" label="Total" class="!w-24 hidden sm:table-cell" @sort="sort_toggle" />
                            <SortHeader column="duplicate_count" :sort_column="sort_column" :sort_direction="sort_direction" label="Duplicates" class="!w-24 hidden sm:table-cell" @sort="sort_toggle" />
                        </tr>
                    </thead>
                    <tbody>
                        <template v-for="(request, request_index) in requests_filtered" :key="request_index">
                            <tr class="cursor-pointer hover:bg-white/[0.03]" @click="request_toggle(request_index)">
                                <td class="w-6 px-1 sm:px-2.5 py-2.5 border-b border-white/[0.04]">
                                    <ChevronRight :size="12" class="inline-block opacity-30 transition-transform" :class="{ 'rotate-90': requests_expanded[request_index] }" />
                                </td>
                                <td class="w-16 px-2 py-2.5 border-b border-white/[0.04]">
                                    <span class="inline-block px-1.5 py-px rounded text-[11px] font-bold" :class="request.is_ajax ? 'bg-purple-700 text-white' : 'bg-blue-600 text-white'">{{ request.is_ajax ? 'AJAX' : 'PAGE' }}</span>
                                </td>
                                <td class="w-16 sm:w-20 px-2 py-2.5 border-b border-white/[0.04] font-semibold">{{ request.method }}</td>
                                <td class="px-2 py-2.5 border-b border-white/[0.04] opacity-70 overflow-hidden text-ellipsis whitespace-nowrap max-w-0" :title="request.path">{{ request.path }}</td>
                                <td class="w-16 px-2 py-2.5 border-b border-white/[0.04] font-semibold hidden sm:table-cell" :class="request.status_code >= 400 ? 'text-red-500' : ''">{{ request.status_code }}</td>
                                <td class="w-[70px] px-2 py-2.5 border-b border-white/[0.04]" :class="request.query_count > 10 ? 'text-orange-500 font-semibold' : ''">{{ request.query_count }}</td>
                                <td class="w-20 sm:w-24 px-2 py-2.5 border-b border-white/[0.04] font-mono whitespace-nowrap">{{ request.query_time }} ms</td>
                                <td class="w-24 px-2 py-2.5 border-b border-white/[0.04] font-mono whitespace-nowrap hidden sm:table-cell">{{ request.duration }} ms</td>
                                <td class="w-24 px-2 py-2.5 border-b border-white/[0.04] opacity-45 hidden sm:table-cell" :class="request.duplicate_count > 0 ? 'text-orange-500 font-semibold' : ''">{{ request.duplicate_count || '' }}</td>
                            </tr>
                            <tr v-if="requests_expanded[request_index]">
                                <td colspan="9" class="!p-0 !px-1 sm:!px-2.5 !pb-4 border-b border-white/[0.06]">
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
                                        <table class="w-full border-collapse min-w-[350px] sm:min-w-[500px]">
                                            <thead>
                                                <tr>
                                                    <SortHeader :column="'index'" :sort_column="query_sort_column(request_index)" :sort_direction="query_sort_direction(request_index)" label="#" class="!w-5 hidden sm:table-cell" @sort="query_sort_toggle(request_index, 'index')" />
                                                    <th class="w-[120px] px-2 py-1.5 text-left text-[11px] font-semibold opacity-40 hidden sm:table-cell">Bar</th>
                                                    <SortHeader :column="'time_ms'" :sort_column="query_sort_column(request_index)" :sort_direction="query_sort_direction(request_index)" label="Time" class="!w-[60px] sm:!w-[90px]" @sort="query_sort_toggle(request_index, 'time_ms')" />
                                                    <th class="w-[60px] px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">Dup</th>
                                                    <th class="px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">SQL</th>
                                                    <th class="w-8 px-2 py-1.5" />
                                                </tr>
                                            </thead>
                                            <tbody>
                                                <tr
                                                    v-for="query in queries_get(request, request_index)"
                                                    :key="query.index"
                                                    class="cursor-pointer hover:bg-white/[0.03]"
                                                    @click.stop="query_open(query, query.index)"
                                                >
                                                    <td class="w-5 px-2 py-1.5 text-[13px] opacity-30 border-t border-white/[0.04] align-top hidden sm:table-cell">{{ query.index + 1 }}</td>
                                                    <td class="w-[120px] px-2 py-1.5 border-t border-white/[0.04] align-middle hidden sm:table-cell">
                                                        <div class="h-2 rounded-full bg-white/[0.06] overflow-hidden">
                                                            <div class="h-full rounded-full" :style="{ width: width_bar(query.time_ms) + '%', backgroundColor: color_bar(query.time_ms) }" />
                                                        </div>
                                                    </td>
                                                    <td class="w-[60px] sm:w-[90px] px-2 py-1.5 border-t border-white/[0.04] align-top" :class="[query.time_ms >= 10 ? 'text-orange-500 font-semibold' : '']">{{ query.time_ms.toFixed(1) }}</td>
                                                    <td class="w-[60px] px-2 py-1.5 border-t border-white/[0.04]">
                                                        <span v-if="query.duplicate_count > 1" class="inline-block bg-orange-600 text-white px-1.5 py-px rounded text-[11px] font-bold">x{{ query.duplicate_count }}</span>
                                                    </td>
                                                    <td class="px-2 py-1.5 border-t border-white/[0.04] align-top max-w-0">
                                                        <span class="font-mono text-xs leading-relaxed whitespace-nowrap overflow-hidden text-ellipsis block">{{ query.sql }}</span>
                                                    </td>
                                                    <td class="w-8 px-2 py-1.5 border-t border-white/[0.04]">
                                                        <ChevronRight :size="14" class="inline-block text-purple-400 opacity-60 hover:opacity-100" />
                                                    </td>
                                                </tr>
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
            :title="'Similar Queries (N+1 Detection) — ' + groups_similar.length + ' groups'"
            :value_copy="groups_similar"
        >
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
                        <tr v-for="(group, i) in groups_similar" :key="i" class="hover:bg-white/[0.02]">
                            <td class="w-[60px] px-2 py-1.5 text-[13px] border-t border-white/[0.04]" :class="group.count > 5 ? 'text-orange-500 font-semibold' : ''">{{ group.count }}</td>
                            <td class="w-[80px] px-2 py-1.5 text-[13px] border-t border-white/[0.04]">{{ group.total_time.toFixed(2) }} ms</td>
                            <td class="px-2 py-1.5 border-t border-white/[0.04]">
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
