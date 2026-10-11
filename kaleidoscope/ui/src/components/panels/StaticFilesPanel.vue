<script setup lang="ts">
import { ref, computed } from 'vue';
import { rows_hidden_count, rows_visible } from '../../services/table';
import CollapsibleSection from '../CollapsibleSection.vue';
import FilterInput from '../FilterInput.vue';
import PanelHeader from '../PanelHeader.vue';
import RowsMore from '../RowsMore.vue';

interface StaticFile {
    finder: string;
    full_path: string;
    path: string;
}

interface StaticFileKeyed extends StaticFile {
    _key: string;
}

interface StaticFileUsed {
    key: string;
    path: string;
}

interface StaticFilesPanelData {
    all_count?: number;
    all_files?: StaticFile[];
    used_count?: number;
    used_files?: string[];
}

const props = defineProps<{
    data: StaticFilesPanelData;
}>();

const text_filter_used = ref('');
const text_filter_all = ref('');
const files_complete = ref(false);

const files_used_keyed = computed(function(): StaticFileUsed[] {
    return (props.data.used_files ?? []).map(function(path, index) {
        if (typeof path !== 'string') {
            throw new TypeError('a static path must be text: ' + String(path));
        }

        return { key: index + ':' + path, path: path };
    });
});

const files_all_keyed = computed(function(): StaticFileKeyed[] {
    return (props.data.all_files ?? []).map(function(file, index) {
        if (typeof file.full_path !== 'string') {
            throw new TypeError('a static file path must be text: ' + String(file.full_path));
        }

        return { ...file, _key: index + ':' + file.full_path };
    });
});

const files_used_filtered = computed(function(): StaticFileUsed[] {
    const search = text_filter_used.value.toLowerCase();

    if (!search) return files_used_keyed.value;

    return files_used_keyed.value.filter(function(file) {
        return file.path.toLowerCase().includes(search);
    });
});

const files_all_filtered = computed(function(): StaticFileKeyed[] {
    const search = text_filter_all.value.toLowerCase();

    if (!search) return files_all_keyed.value;

    return files_all_keyed.value.filter(function(file) {
        return file.path.toLowerCase().includes(search) || file.full_path.toLowerCase().includes(search);
    });
});

const files_used_copy = computed(function(): string {
    return (props.data.used_files ?? []).join('\n');
});
</script>

<template>
    <div>
        <PanelHeader
            :stats="[
                { label: 'Used', value: data.used_count ?? 0 },
                { label: 'Total', value: data.all_count ?? 0 },
            ]"
        />

        <CollapsibleSection
            title="Static Files"
            :count="data.used_count"
            :value_copy="files_used_copy"
        >
            <div v-if="data.used_files && data.used_files.length" class="mb-4 pl-2">
                <FilterInput v-model="text_filter_used" />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table v-if="files_used_filtered.length" class="w-full border-collapse min-w-[250px]">
                    <tbody>
                        <tr v-for="file in files_used_filtered" :key="file.key" class="hover:bg-white/2">
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ file.path }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div v-if="!data.used_files || !data.used_files.length" class="py-6 text-center opacity-30 italic text-[13px]">No static files detected in response</div>
        </CollapsibleSection>

        <CollapsibleSection
            title="All Static Files"
            :count="data.all_count"
            :value_copy="data.all_files"
        >
            <div class="mb-4 pl-2">
                <FilterInput v-model="text_filter_all" />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[300px]">
                    <thead>
                        <tr>
                            <th class="px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/8 select-none">Path</th>
                            <th class="w-32 sm:w-48 px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/8 select-none hidden sm:table-cell">Finder</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="file in rows_visible(files_all_filtered, files_complete)" :key="file._key" class="hover:bg-white/2">
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 overflow-hidden text-ellipsis whitespace-nowrap" :title="file.full_path">{{ file.path }}</td>
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] border-t border-white/4 opacity-45 hidden sm:table-cell">{{ file.finder }}</td>
                        </tr>
                        <RowsMore
                            v-if="rows_hidden_count(files_all_filtered, files_complete) > 0"
                            :columns="2"
                            :hidden_count="rows_hidden_count(files_all_filtered, files_complete)"
                            @more="files_complete = true"
                        />
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>
    </div>
</template>
