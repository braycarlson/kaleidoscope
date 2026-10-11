<script setup lang="ts">
import { ref, computed } from 'vue';
import { use_sort } from '../../composables/use_sort';
import CollapsibleSection from '../CollapsibleSection.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
import SortHeader from './SortHeader.vue';

interface CategoryStyle {
    text: string;
    background: string;
    dot: string;
}

interface MemoryRow {
    category: string;
    count: number;
    size: number;
    size_display: string;
    type: string;
}

interface MemoryPanelData {
    diff?: MemoryRow[];
    error?: string;
    total_objects?: number;
    total_size_display?: string;
}

type Category = 'builtin' | 'django' | 'project' | 'stdlib';

const CATEGORY_STYLES: Record<Category, CategoryStyle> = {
    'builtin': { text: 'text-blue-400', background: 'bg-blue-500', dot: 'bg-blue-400' },
    'stdlib':  { text: 'text-cyan-400', background: 'bg-cyan-500', dot: 'bg-cyan-400' },
    'django':  { text: 'text-green-400', background: 'bg-green-500', dot: 'bg-green-400' },
    'project': { text: 'text-purple-400', background: 'bg-purple-500', dot: 'bg-purple-400' },
};

const CATEGORY_KEYS = Object.keys(CATEGORY_STYLES);

const props = defineProps<{
    data: MemoryPanelData;
}>();

const text_filter = ref('');
const show_allocated = ref(true);
const show_freed = ref(true);
const show_unchanged = ref(false);
const category_active = ref<string | null>(null);

const rows_filtered = computed(function(): MemoryRow[] {
    const rows: MemoryRow[] = props.data.diff ?? [];
    const search = text_filter.value.toLowerCase();

    return rows.filter(function(row) {
        if (row.count > 0 && !show_allocated.value) return false;
        if (row.count < 0 && !show_freed.value) return false;
        if (row.count === 0 && !show_unchanged.value) return false;
        if (category_active.value && row.category !== category_active.value) return false;
        if (search && !row.type.toLowerCase().includes(search)) return false;
        return true;
    });
});

const { sort_column, sort_direction, sorted: diff_sorted, sort_toggle } = use_sort(rows_filtered, 'size', 'desc');

const stats = computed(function() {
    const rows: MemoryRow[] = props.data.diff ?? [];
    let allocated = 0;
    let freed = 0;
    let unchanged = 0;

    for (const row of rows) {
        if (row.count > 0) {
            allocated++;
        }

        if (row.count < 0) {
            freed++;
        }

        if (row.count === 0) {
            unchanged++;
        }
    }

    return { allocated, freed, unchanged };
});

const stats_header = computed(function() {
    const items: { label: string; value: string | number }[] = [];

    if (props.data.total_size_display) {
        items.push({ label: 'Total Size', value: props.data.total_size_display });
    }

    if (props.data.total_objects) {
        items.push({ label: 'Total Objects', value: props.data.total_objects.toLocaleString() });
    }

    items.push({ label: 'Showing', value: diff_sorted.value.length });

    return items;
});

const stats_category = computed(function() {
    const rows: MemoryRow[] = props.data.diff ?? [];
    const counts: Record<string, number> = {};

    for (const row of rows) {
        const category = row.category || 'project';
        counts[category] = (counts[category] ?? 0) + 1;
    }

    return counts;
});

function category_toggle(category: string) {
    category_active.value = category_active.value === category ? null : category;
}

function class_row(row: MemoryRow): string {
    if (!Number.isFinite(row.count)) {
        throw new RangeError('a memory row count must be a finite number: ' + row.count);
    }

    if (row.count > 0) return 'text-red-400';
    if (row.count < 0) return 'text-green-400';
    return 'opacity-30';
}

function class_size(row: MemoryRow): string {
    if (!Number.isFinite(row.size)) {
        throw new RangeError('a memory row size must be a finite number: ' + row.size);
    }

    if (row.size > 0) return 'text-red-400';
    if (row.size < 0) return 'text-green-400';
    return 'opacity-30';
}

function is_category(value: string): value is Category {
    return Object.hasOwn(CATEGORY_STYLES, value);
}

function style_for(category: string): CategoryStyle {
    if (typeof category !== 'string') {
        throw new TypeError('a memory category must be text: ' + String(category));
    }

    if (is_category(category)) return CATEGORY_STYLES[category];

    return CATEGORY_STYLES.project;
}
</script>

<template>
    <div>
        <div v-if="data.error" class="py-10 text-center text-red-400 italic">{{ data.error }}</div>

        <template v-else>
            <PanelHeader :stats="stats_header" />

            <CollapsibleSection
                v-if="diff_sorted.length || (data.diff && data.diff.length)"
                title="Memory"
                :count="(data.diff || []).length"
                :value_copy="data.diff"
            >
                <div class="mb-4 pl-2">
                    <FilterInput v-model="text_filter" placeholder="Filter..." />
                </div>

                <div class="mb-4 flex flex-col gap-5 pl-2">
                    <div class="flex items-center gap-3 sm:gap-5 flex-wrap">
                        <span class="opacity-40 text-[12px]">Show</span>

                        <div class="flex items-center gap-2 cursor-pointer" @click="show_allocated = !show_allocated">
                            <div class="relative w-7 h-4 rounded-full transition-colors" :class="show_allocated ? 'bg-red-600' : 'bg-white/10'">
                                <div class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform" :class="{ 'translate-x-3': show_allocated }" />
                            </div>
                            <span class="text-[12px]" :class="show_allocated ? 'text-red-400' : 'opacity-40'">Allocated ({{ stats.allocated }})</span>
                        </div>

                        <div class="flex items-center gap-2 cursor-pointer" @click="show_freed = !show_freed">
                            <div class="relative w-7 h-4 rounded-full transition-colors" :class="show_freed ? 'bg-green-600' : 'bg-white/10'">
                                <div class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform" :class="{ 'translate-x-3': show_freed }" />
                            </div>
                            <span class="text-[12px]" :class="show_freed ? 'text-green-400' : 'opacity-40'">Freed ({{ stats.freed }})</span>
                        </div>

                        <div class="flex items-center gap-2 cursor-pointer" @click="show_unchanged = !show_unchanged">
                            <div class="relative w-7 h-4 rounded-full transition-colors" :class="show_unchanged ? 'bg-gray-500' : 'bg-white/10'">
                                <div class="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform" :class="{ 'translate-x-3': show_unchanged }" />
                            </div>
                            <span class="text-[12px]" :class="show_unchanged ? 'text-gray-300' : 'opacity-40'">Unchanged ({{ stats.unchanged }})</span>
                        </div>
                    </div>

                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="opacity-40 text-[12px]">Category</span>

                        <button
                            v-for="category in CATEGORY_KEYS"
                            :key="category"
                            class="flex items-center gap-1.5 px-2 py-0.5 rounded-sm text-[11px] transition-colors cursor-pointer"
                            :class="category_active === category
                                ? style_for(category).background + ' text-white'
                                : category_active === null
                                    ? style_for(category).text + ' bg-white/5'
                                    : 'opacity-30 bg-white/3'"
                            @click="category_toggle(category)"
                        >
                            <span class="w-1.5 h-1.5 rounded-full" :class="style_for(category).dot" />
                            {{ category }} ({{ stats_category[category] || 0 }})
                        </button>
                    </div>
                </div>

                <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                    <table class="w-full border-collapse min-w-[400px]">
                        <thead>
                            <tr>
                                <SortHeader column="type" :sort_column="sort_column" :sort_direction="sort_direction" label="Type" @sort="sort_toggle" />
                                <SortHeader column="category" :sort_column="sort_column" :sort_direction="sort_direction" label="Category" class="w-24! hidden sm:table-cell" @sort="sort_toggle" />
                                <SortHeader column="count" :sort_column="sort_column" :sort_direction="sort_direction" label="Count" class="w-20! sm:w-24!" @sort="sort_toggle" />
                                <SortHeader column="size" :sort_column="sort_column" :sort_direction="sort_direction" label="Size" class="w-24! sm:w-28!" @sort="sort_toggle" />
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(row, i) in diff_sorted" :key="i" class="hover:bg-white/2">
                                <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4" :class="class_row(row)">{{ row.type }}</td>
                                <td class="w-24 px-2 py-1.5 text-[13px] border-t border-white/4 hidden sm:table-cell" :class="style_for(row.category || 'project').text">{{ row.category || 'project' }}</td>
                                <td class="w-20 sm:w-24 px-2 py-1.5 text-[13px] font-mono border-t border-white/4" :class="class_row(row)">{{ row.count > 0 ? '+' : '' }}{{ row.count }}</td>
                                <td class="w-24 sm:w-28 px-2 py-1.5 text-[13px] font-mono border-t border-white/4" :class="class_size(row)">{{ row.size_display }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </CollapsibleSection>
            <div v-if="!diff_sorted.length && !(data.diff && data.diff.length)" class="py-10 text-center opacity-30 italic">No memory data captured yet. Enable the panel, then navigate to a page.</div>
        </template>
    </div>
</template>
