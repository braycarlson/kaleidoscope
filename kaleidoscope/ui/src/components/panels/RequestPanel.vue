<script setup lang="ts">
import CollapsibleSection from '../CollapsibleSection.vue';
import PanelHeader from '../PanelHeader.vue';
import { value_format } from '../../services/format';

interface ViewData {
    args: unknown[];
    func: string;
    kwargs: Record<string, unknown>;
    url_name: string;
}

interface RequestPanelData {
    cookies?: Record<string, string>;
    get?: Record<string, string>;
    headers?: Record<string, string>;
    method: string;
    path: string;
    post?: Record<string, string>;
    response_headers?: Record<string, string>;
    status_code: number;
    view?: ViewData;
}

defineProps<{
    data: RequestPanelData;
}>();

function count_entries(object: Record<string, string> | undefined): number {
    return object ? Object.keys(object).length : 0;
}
</script>

<template>
    <div>
        <PanelHeader
            :stats="[
                { label: 'Method', value: data.method },
                { label: 'Status', value: data.status_code },
                { label: 'Path', value: data.path },
            ]"
        />

        <CollapsibleSection
            v-if="data.view"
            title="View"
            :value_copy="data.view"
        >
            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[300px]">
                    <tbody>
                        <tr class="hover:bg-white/[0.02]">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/[0.04] align-top font-semibold whitespace-nowrap">Function</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ data.view.func }}</td>
                        </tr>
                        <tr v-if="data.view.url_name" class="hover:bg-white/[0.02]">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/[0.04] align-top font-semibold whitespace-nowrap">URL Name</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ data.view.url_name }}</td>
                        </tr>
                        <tr v-if="data.view.args && data.view.args.length" class="hover:bg-white/[0.02]">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/[0.04] align-top font-semibold whitespace-nowrap">Args</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ value_format(data.view.args) }}</td>
                        </tr>
                        <tr v-if="data.view.kwargs && Object.keys(data.view.kwargs).length" class="hover:bg-white/[0.02]">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/[0.04] align-top font-semibold whitespace-nowrap">Kwargs</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ value_format(data.view.kwargs) }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>

        <template
            v-for="section in [
                { label: 'GET Parameters', data: data.get },
                { label: 'POST Parameters', data: data.post },
                { label: 'Request Headers', data: data.headers },
                { label: 'Response Headers', data: data.response_headers },
                { label: 'Cookies', data: data.cookies },
            ]"
            :key="section.label"
        >
            <CollapsibleSection
                v-if="section.data && count_entries(section.data) > 0"
                :title="section.label"
                :count="count_entries(section.data)"
                :value_copy="section.data"
            >
                <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                    <table class="w-full border-collapse min-w-[300px]">
                        <tbody>
                            <tr v-for="(value, key) in section.data" :key="key" class="hover:bg-white/[0.02]">
                                <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/[0.04] align-top font-semibold whitespace-nowrap">{{ key }}</td>
                                <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/[0.04] break-all">{{ value }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </CollapsibleSection>
        </template>

        <div v-if="!data.view && !count_entries(data.headers)" class="py-10 text-center opacity-30 italic">No request captured</div>
    </div>
</template>
