<script setup lang="ts">
import { ref, computed } from 'vue';
import { ChevronRight } from 'lucide-vue-next';
import { use_sort } from '../../composables/use_sort';
import CollapsibleSection from '../CollapsibleSection.vue';
import CopyButton from '../CopyButton.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
import SortHeader from './SortHeader.vue';

interface SettingsEntry {
    expandable: boolean;
    value_full: string;
    key: string;
    preview: string;
    value: unknown;
    value_string: string;
}

interface SettingsPanelData {
    settings: Record<string, unknown>;
}

const props = defineProps<{
    data: SettingsPanelData;
}>();

const text_filter = ref('');
const expanded = ref<Record<string, boolean>>({});

const entries = computed(function(): SettingsEntry[] {
    const items: Record<string, unknown> = props.data.settings || {};
    const search = text_filter.value.toLowerCase();
    const list: SettingsEntry[] = [];

    for (const key of Object.keys(items)) {
        if (search && !key.toLowerCase().includes(search) && !String(items[key]).toLowerCase().includes(search)) {
            continue;
        }

        const value = items[key];

        list.push({
            expandable: is_expandable(value),
            value_full: full_format(value),
            key: key,
            preview: preview_format(value),
            value: value,
            value_string: String(value),
        });
    }

    return list;
});

const { sort_column, sort_direction, sorted: settings_sorted, sort_toggle } = use_sort(entries, 'key', 'asc');

function is_expandable(value: unknown): boolean {
    if (value === null || value === undefined) return false;
    if (typeof value === 'string' && value.length > 80) return true;
    if (typeof value === 'object') return true;
    return false;
}

function preview_format(value: unknown): string {
    if (value === null) return 'None';
    if (value === undefined) return 'undefined';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'string') {
        if (value === '********') return '********';
        if (value.length > 80) return value.substring(0, 77) + '...';
        return value;
    }
    if (Array.isArray(value)) return value.length === 0 ? '[]' : '[...]';
    if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length === 0 ? '{}' : '{...}';
    return String(value);
}

function full_format(value: unknown): string {
    if (value === null) return 'None';
    if (value === undefined) return 'undefined';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'string') return value;
    return JSON.stringify(value, null, 2);
}

function expanded_toggle(key: string) {
    expanded.value = { ...expanded.value, [key]: !expanded.value[key] };
}
</script>

<template>
    <div>
        <PanelHeader
            :stats="[
                { label: 'Settings', value: Object.keys(data.settings || {}).length },
            ]"
        />

        <CollapsibleSection
            title="Django Settings"
            :count="settings_sorted.length"
            :value_copy="data.settings"
        >
            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter" placeholder="Filter..." />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[400px]">
                    <thead>
                        <tr>
                            <SortHeader column="key" :sort_column="sort_column" :sort_direction="sort_direction" label="Setting" class="!w-48 sm:!w-72" @sort="sort_toggle" />
                            <SortHeader column="value_string" :sort_column="sort_column" :sort_direction="sort_direction" label="Value" @sort="sort_toggle" />
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="entry in settings_sorted"
                            :key="entry.key"
                            class="hover:bg-white/[0.02]"
                            :class="entry.expandable ? 'cursor-pointer' : ''"
                            @click="entry.expandable ? expanded_toggle(entry.key) : undefined"
                        >
                            <td class="w-48 sm:w-72 px-2 py-1.5 text-[13px] font-semibold border-t border-white/[0.04] align-top">{{ entry.key }}</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04]">
                                <div v-if="!expanded[entry.key]" class="flex items-center gap-2 overflow-hidden">
                                    <ChevronRight v-if="entry.expandable" :size="12" class="opacity-30 shrink-0" />
                                    <span class="overflow-hidden text-ellipsis whitespace-nowrap" :class="entry.preview === '********' ? 'opacity-30' : ''">{{ entry.preview }}</span>
                                </div>
                                <div v-else>
                                    <div class="flex items-start gap-2">
                                        <ChevronRight :size="12" class="opacity-30 shrink-0 mt-0.5 rotate-90" />
                                        <pre class="whitespace-pre-wrap break-all text-[12px] leading-relaxed flex-1">{{ entry.value_full }}</pre>
                                        <CopyButton :value="entry.key + '=' + entry.value_full" :size="11" />
                                    </div>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>
    </div>
</template>
