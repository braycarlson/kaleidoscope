<script setup lang="ts">
import { X } from 'lucide-vue-next';
import CollapsibleSection from '../CollapsibleSection.vue';
import type { StackFrame } from '../../types';

interface QueryData {
    duplicate_count: number;
    explain?: string;
    many: boolean;
    params: string | null;
    raw_sql: string | null;
    sql: string;
    stack: StackFrame[];
    time_ms: number;
}

defineProps<{
    query: QueryData;
    index: number;
    duplicate_count?: number;
}>();

const emit = defineEmits<{
    close: [];
}>();

function sql_format(sql: string): string {
    const keywords = [
        'FROM', 'WHERE', 'AND', 'OR', 'ORDER BY', 'GROUP BY',
        'HAVING', 'LIMIT', 'OFFSET', 'LEFT JOIN', 'RIGHT JOIN',
        'INNER JOIN', 'OUTER JOIN', 'JOIN', 'ON', 'SET', 'VALUES', 'UNION',
    ];

    let formatted = sql;

    for (let index = 0; index < keywords.length; index++) {
        const keyword = keywords[index];
        const pattern = new RegExp('\\b(' + keyword + ')\\b', 'gi');
        formatted = formatted.replace(pattern, '\n$1');
    }

    return formatted.trim();
}
</script>

<template>
    <div class="fixed inset-0 z-[1000001] flex items-stretch justify-end">
        <div class="flex-1 bg-black/40 hidden sm:block" @click="emit('close')" />
        <div class="w-full sm:w-[700px] sm:max-w-[80vw] bg-[#12121e] border-l border-white/10 flex flex-col overflow-hidden">
            <div class="flex items-center justify-between px-3 sm:px-5 py-3 border-b border-white/[0.08] bg-[#0e0e1a] shrink-0">
                <span class="font-semibold text-sm">Query #{{ index + 1 }}</span>
                <div class="flex items-center shrink-0">
                    <button class="text-gray-500 hover:text-white" @click="emit('close')">
                        <X :size="18" />
                    </button>
                </div>
            </div>
            <div class="flex-1 overflow-y-auto p-3 sm:p-5">
                <div class="flex flex-wrap items-center gap-3 sm:gap-5 pb-4 mb-5 border-b border-white/[0.08]">
                    <div class="flex items-center gap-2">
                        <span class="opacity-40 text-[13px]">Duration</span>
                        <span class="font-semibold text-[15px]" :class="query.time_ms >= 10 ? 'text-orange-500' : ''">{{ query.time_ms.toFixed(2) }} ms</span>
                    </div>
                    <div v-if="query.many" class="flex items-center gap-2">
                        <span class="opacity-40 text-[13px]">Type</span>
                        <span class="font-semibold text-[15px] text-purple-400">executemany</span>
                    </div>
                    <div v-if="(duplicate_count || 0) > 1" class="flex items-center gap-2">
                        <span class="opacity-40 text-[13px]">Duplicates</span>
                        <span class="font-semibold text-[15px] text-orange-500">{{ duplicate_count }}</span>
                    </div>
                </div>

                <CollapsibleSection title="SQL" :value_copy="query.sql">
                    <pre class="font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{{ sql_format(query.sql) }}</pre>
                </CollapsibleSection>

                <CollapsibleSection v-if="query.raw_sql" title="Raw SQL" :value_copy="query.raw_sql">
                    <pre class="font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{{ sql_format(query.raw_sql) }}</pre>
                </CollapsibleSection>

                <CollapsibleSection v-if="query.params" title="Parameters" :value_copy="query.params">
                    <pre class="font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{{ query.params }}</pre>
                </CollapsibleSection>

                <CollapsibleSection v-if="query.explain" title="EXPLAIN" :value_copy="query.explain">
                    <pre class="font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{{ query.explain }}</pre>
                </CollapsibleSection>

                <CollapsibleSection v-if="query.stack && query.stack.length" title="Stack Trace" :value_copy="query.stack">
                    <div class="rounded border border-white/[0.06] overflow-hidden">
                        <div
                            v-for="(frame, i) in query.stack"
                            :key="i"
                            class="px-3 py-2 border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02]"
                        >
                            <div class="flex items-baseline gap-2">
                                <span class="font-mono text-[12px] text-blue-400 shrink-0">{{ frame.function }}</span>
                                <span class="font-mono text-[11px] opacity-30 overflow-hidden text-ellipsis whitespace-nowrap" :title="frame.file">{{ frame.file }}:{{ frame.line }}</span>
                            </div>
                            <div v-if="frame.text" class="font-mono text-[11px] opacity-40 mt-0.5 pl-2 border-l-2 border-white/[0.06]">{{ frame.text }}</div>
                        </div>
                    </div>
                </CollapsibleSection>
            </div>
        </div>
    </div>
</template>
