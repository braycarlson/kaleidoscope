<script setup lang="ts">
import { ref, computed } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import FilterInput from '../FilterInput.vue';

interface StaticFile {
    finder: string;
    full_path: string;
    path: string;
}

interface StaticFilesPanelData {
    all_count: number;
    all_files: StaticFile[];
    used_count: number;
    used_files: string[];
}

const props = defineProps<{
    data: StaticFilesPanelData;
}>();

const text_filter = ref('');

const files_all_filtered = computed(function(): StaticFile[] {
    const search = text_filter.value.toLowerCase();

    if (!search) return props.data.all_files || [];

    return (props.data.all_files || []).filter(function(file: StaticFile) {
        return file.path.toLowerCase().includes(search) || file.full_path.toLowerCase().includes(search);
    });
});

const files_used_copy = computed(function(): string {
    return (props.data.used_files || []).join('\n');
});
</script>

<template>
    <div>
        <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-5 border-b border-white/[0.08]">
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Used</span>
                <span class="font-semibold text-[15px]">{{ data.used_count }}</span>
            </div>
            <div class="flex items-center gap-2">
                <span class="opacity-40 text-[13px]">Total Available</span>
                <span class="font-semibold text-[15px]">{{ data.all_count }}</span>
            </div>
        </div>

        <CollapsibleSection
            title="Static Files"
            :count="data.used_count"
            :value_copy="files_used_copy"
        >
            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table v-if="data.used_files && data.used_files.length" class="w-full border-collapse min-w-[250px]">
                    <tbody>
                        <tr v-for="file in data.used_files" :key="file" class="hover:bg-white/[0.02]">
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ file }}</td>
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
                <FilterInput v-model="text_filter" />
            </div>

            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[300px]">
                    <thead>
                        <tr>
                            <th class="px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/[0.08] select-none">Path</th>
                            <th class="w-32 sm:w-48 px-2 py-2 text-left text-xs font-semibold opacity-40 border-b border-white/[0.08] select-none hidden sm:table-cell">Finder</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="file in files_all_filtered" :key="file.path" class="hover:bg-white/[0.02]">
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] overflow-hidden text-ellipsis whitespace-nowrap" :title="file.full_path">{{ file.path }}</td>
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] border-t border-white/[0.04] opacity-45 hidden sm:table-cell">{{ file.finder }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>
    </div>
</template>
