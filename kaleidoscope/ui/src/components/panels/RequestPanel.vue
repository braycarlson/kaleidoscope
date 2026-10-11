<script setup lang="ts">
import { computed } from 'vue';
import CollapsibleSection from '../CollapsibleSection.vue';
import PanelHeader from '../PanelHeader.vue';
import { value_format } from '../../services/format';

interface ViewData {
    args: unknown[];
    func: string;
    kwargs: Record<string, unknown>;
    url_name: string;
}

interface PermissionCheck {
    count: number;
    kind: string;
    name: string;
    result: boolean;
    superuser: boolean;
    target: string;
}

interface SessionData {
    accessed: boolean;
    backend: string;
    expire_at_browser_close: boolean;
    expiry_age: number;
    items: Record<string, unknown>;
    modified: boolean;
}

interface UserData {
    active: boolean;
    authenticated: boolean;
    id: string;
    name: string;
    staff: boolean;
    superuser: boolean;
}

interface RequestPanelData {
    cookies?: Record<string, string>;
    get?: Record<string, string>;
    headers?: Record<string, string>;
    method?: string;
    path?: string;
    permissions?: PermissionCheck[];
    post?: Record<string, string>;
    response_headers?: Record<string, string>;
    session?: SessionData | null;
    status_code?: number;
    user?: UserData | null;
    view?: ViewData;
}

const props = defineProps<{
    data: RequestPanelData;
}>();

function count_entries(object: Record<string, unknown> | undefined): number {
    if (!object) return 0;

    if (typeof object !== 'object') {
        throw new TypeError('request data must be a record, not ' + typeof object);
    }

    if (Array.isArray(object)) throw new TypeError('request data must be a record, not a list');
    return Object.keys(object).length;
}

function expiry_text(session: SessionData): string {
    if (session.expire_at_browser_close) return 'when the browser closes';

    const seconds = session.expiry_age;

    if (!Number.isFinite(seconds)) {
        throw new RangeError('a session expiry must be finite: ' + seconds);
    }

    if (seconds < 60) return 'in ' + seconds + ' s';
    if (seconds < 3_600) return 'in ' + Math.floor(seconds / 60) + ' min';
    if (seconds < 86_400) return 'in ' + Math.floor(seconds / 3_600) + ' h';
    return 'in ' + Math.floor(seconds / 86_400) + ' d';
}

const permissions = computed(function(): PermissionCheck[] {
    const checks = props.data.permissions ?? [];

    for (const check of checks) {
        if (!Number.isFinite(check.count)) {
            throw new RangeError('a permission check count must be finite: ' + check.count);
        }
    }

    return checks;
});

function session_rows(session: SessionData): [string, unknown][] {
    return [
        ['Backend', session.backend],
        ['Accessed', session.accessed],
        ['Modified', session.modified],
        ['Expires', expiry_text(session)],
    ];
}

function user_rows(user: UserData): [string, unknown][] {
    return [
        ['Name', user.name],
        ['ID', user.id],
        ['Authenticated', user.authenticated],
        ['Active', user.active],
        ['Staff', user.staff],
        ['Superuser', user.superuser],
    ];
}
</script>

<template>
    <div>
        <PanelHeader
            :stats="[
                { label: 'Method', value: data.method ?? '' },
                { label: 'Status', value: data.status_code ?? '' },
                { label: 'Path', value: data.path ?? '' },
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
                        <tr class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">Function</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ data.view.func }}</td>
                        </tr>
                        <tr v-if="data.view.url_name" class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">URL Name</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ data.view.url_name }}</td>
                        </tr>
                        <tr v-if="data.view.args && data.view.args.length" class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">Args</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ value_format(data.view.args) }}</td>
                        </tr>
                        <tr v-if="data.view.kwargs && Object.keys(data.view.kwargs).length" class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">Kwargs</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ value_format(data.view.kwargs) }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>

        <CollapsibleSection
            v-if="data.user"
            title="User"
            :value_copy="data.user"
        >
            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[300px]">
                    <tbody>
                        <tr v-for="[label, value] in user_rows(data.user)" :key="label" class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">{{ label }}</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ value_format(value) }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>

        <CollapsibleSection
            v-if="permissions.length"
            title="Permission Checks"
            :count="permissions.length"
            :value_copy="permissions"
        >
            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[300px]">
                    <thead>
                        <tr>
                            <th class="px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">Permission</th>
                            <th class="px-2 py-1.5 text-left text-[11px] font-semibold opacity-40 hidden sm:table-cell">Object</th>
                            <th class="w-36 px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">Result</th>
                            <th class="w-16 px-2 py-1.5 text-left text-[11px] font-semibold opacity-40">Count</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="(check, i) in permissions" :key="i" data-ks="permission-check" class="hover:bg-white/2">
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">
                                {{ check.name }}
                                <span v-if="check.kind === 'module'" class="ml-1 opacity-40 text-[11px]">(module)</span>
                            </td>
                            <td class="px-2 py-1.5 text-[13px] font-mono opacity-60 border-t border-white/4 break-all hidden sm:table-cell">{{ check.target }}</td>
                            <td class="w-36 px-2 py-1.5 text-[13px] border-t border-white/4">
                                <span :class="check.result ? 'text-green-500' : 'text-red-500'">{{ check.result ? 'Granted' : 'Denied' }}</span> <span v-if="check.superuser" class="opacity-50 text-[11px]">as superuser</span>
                            </td>
                            <td class="w-16 px-2 py-1.5 text-[13px] border-t border-white/4">{{ check.count }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </CollapsibleSection>

        <CollapsibleSection
            v-if="data.session"
            title="Session"
            :count="count_entries(data.session.items)"
            :value_copy="data.session"
        >
            <div class="overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0">
                <table class="w-full border-collapse min-w-[300px]">
                    <tbody>
                        <tr v-for="[label, value] in session_rows(data.session)" :key="label" class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">{{ label }}</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ value_format(value) }}</td>
                        </tr>
                        <tr v-for="(value, key) in data.session.items" :key="'item-' + key" data-ks="session-item" class="hover:bg-white/2">
                            <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] border-t border-white/4 align-top font-semibold whitespace-nowrap">{{ key }}</td>
                            <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ value_format(value) }}</td>
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
                            <tr v-for="(value, key) in section.data" :key="key" class="hover:bg-white/2">
                                <td class="w-32 sm:w-48 px-2 py-1.5 text-[13px] opacity-50 border-t border-white/4 align-top font-semibold whitespace-nowrap">{{ key }}</td>
                                <td class="px-2 py-1.5 text-[13px] font-mono border-t border-white/4 break-all">{{ value }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </CollapsibleSection>
        </template>

        <div v-if="!data.view && !count_entries(data.headers)" class="py-10 text-center opacity-30 italic">No request captured</div>
    </div>
</template>
