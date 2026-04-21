<script setup lang="ts">
import { computed } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import PanelHeader from '../PanelHeader.vue';

interface LineEntry {
    hits: number;
    lineno: number;
    pct: number;
    per_hit_ms: number;
    source: string;
    time_ms: number;
}

interface FunctionEntry {
    filename: string;
    full_path: string;
    func_name: string;
    lines: LineEntry[];
    start_lineno: number;
    total_time_ms: number;
}

interface LineProfilerPanelData {
    duration_ms: number;
    error?: string;
    function_count?: number;
    functions: FunctionEntry[];
    has_data?: boolean;
}

const props = defineProps<{
    data: LineProfilerPanelData;
}>();

const functions = computed(function(): FunctionEntry[] {
    return props.data.functions || [];
});

const profile_copy = computed(function(): string {
    return functions.value.map(function(fn) {
        const header = fn.func_name + ' (' + fn.filename + ':' + fn.start_lineno + ') ' + fn.total_time_ms + ' ms';
        const lines = fn.lines.map(function(line) {
            return line.lineno + '\t' + line.hits + '\t' + line.time_ms + 'ms\t' + line.pct + '%\t' + line.source;
        }).join('\n');
        return header + '\n' + lines;
    }).join('\n\n');
});

function class_row(percent: number): string {
    if (percent >= 40) return 'bg-ks-row-critical';
    if (percent >= 20) return 'bg-ks-row-high';
    if (percent >= 10) return 'bg-ks-row-medium';
    if (percent >= 5) return 'bg-ks-row-low';
    return '';
}

function class_time(percent: number): string {
    if (percent >= 40) return 'text-red-400 font-semibold';
    if (percent >= 20) return 'text-orange-400';
    if (percent >= 10) return 'text-yellow-400';
    return '';
}

const stats = computed(function() {
    const items: { label: string; value: string | number }[] = [
        { label: 'Duration', value: (props.data.duration_ms || 0) + ' ms' },
    ];

    if (props.data.function_count) {
        items.push({ label: 'Functions', value: props.data.function_count });
    }

    return items;
});
</script>

<template>
    <div>
        <div v-if="data.error" class="py-10 text-center text-red-400 italic">{{ data.error }}</div>

        <template v-else>
            <PanelHeader :stats="stats" />

            <template v-if="data.has_data && functions.length">
                <CollapsibleSection
                    v-for="(fn, fn_index) in functions"
                    :key="fn_index"
                    :title="fn.func_name"
                    :value_copy="profile_copy"
                >
                    <div class="flex items-baseline gap-3 flex-wrap mb-3 pl-1">
                        <span class="font-mono text-[12px] opacity-50 overflow-hidden text-ellipsis whitespace-nowrap" :title="fn.full_path">{{ fn.filename }}:{{ fn.start_lineno }}</span>
                        <span class="text-[12px] font-mono text-purple-400 ml-auto shrink-0">{{ fn.total_time_ms }} ms</span>
                    </div>

                    <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                        <table class="w-full border-collapse min-w-[500px]">
                            <thead>
                                <tr>
                                    <th class="w-14 px-2 py-1 text-right text-[11px] font-semibold opacity-30 border-b border-ks-section">Line</th>
                                    <th class="w-14 px-2 py-1 text-right text-[11px] font-semibold opacity-30 border-b border-ks-section">Hits</th>
                                    <th class="w-20 px-2 py-1 text-right text-[11px] font-semibold opacity-30 border-b border-ks-section hidden sm:table-cell">Time</th>
                                    <th class="w-16 px-2 py-1 text-right text-[11px] font-semibold opacity-30 border-b border-ks-section">
                                        <span class="flex items-center justify-end gap-1.5">
                                            %
                                            <span class="w-12 h-1.5 rounded-full bg-ks-toggle-off overflow-hidden hidden sm:block" />
                                        </span>
                                    </th>
                                    <th class="px-2 py-1 text-left text-[11px] font-semibold opacity-30 border-b border-ks-section">Source</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="(line, line_index) in fn.lines" :key="line_index" :class="class_row(line.pct)">
                                    <td class="px-2 py-0.5 text-right text-[12px] font-mono opacity-25 border-t border-ks-row">{{ line.lineno }}</td>
                                    <td class="px-2 py-0.5 text-right text-[12px] font-mono opacity-50 border-t border-ks-row">{{ line.hits }}</td>
                                    <td class="px-2 py-0.5 text-right text-[12px] font-mono opacity-40 border-t border-ks-row hidden sm:table-cell">
                                        <span class="flex items-center justify-end gap-1.5" :class="class_time(line.pct)">
                                            <span v-if="line.time_ms > 0" class="w-12 h-1.5 rounded-full bg-ks-toggle-off overflow-hidden hidden sm:block">
                                                <div class="h-full rounded-full bg-current" :style="{ width: Math.min(100, line.pct) + '%' }" />
                                            </span>
                                            {{ line.time_ms.toFixed(2) }}
                                        </span>
                                    </td>
                                    <td class="px-2 py-0.5 text-right text-[12px] font-mono border-t border-ks-row" :class="class_time(line.pct)">{{ line.pct.toFixed(1) }}%</td>
                                    <td class="px-2 py-0.5 text-[12px] font-mono border-t border-ks-row whitespace-pre overflow-hidden text-ellipsis">{{ line.source }}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </CollapsibleSection>
            </template>
            <div v-else class="py-10 text-center opacity-30 italic">No line profiler data captured yet. Enable the panel, then navigate to a page.</div>
        </template>
    </div>
</template>
