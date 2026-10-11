<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { ChevronRight } from 'lucide-vue-next';
import { fetch_native } from '../../services/api';
import PrismCode from './PrismCode.vue';

interface PathStep {
    kind: 'key' | 'attr' | 'item';
    name?: string;
    index?: number;
}

interface ChildEntry {
    label: string;
    preview: string;
    has_children: boolean;
    step: PathStep;
}

interface ValueData {
    type: string;
    value?: string | boolean;
    repr?: string;
    truncated?: number;
    class_name?: string;
    model?: string;
    pk?: string;
    name?: string;
    size?: number;
    items?: ChildEntry[];
    attributes?: ChildEntry[];
    error?: string;
}

const CONTAINER_TYPES: readonly string[] = ['dict', 'list', 'tuple', 'set', 'object', 'model', 'queryset', 'enum'];

const props = defineProps<{
    template_index: number;
    path: PathStep[];
    label?: string;
    preview?: string;
    separator?: string;
    initial?: ValueData;
    has_children?: boolean;
    depth?: number;
    auto_expand?: boolean;
}>();

const expanded = ref(props.auto_expand);
const loaded_value = ref<ValueData | null>(props.initial ?? null);
const loading = ref(false);
const error = ref<string | null>(null);

const can_expand = computed(function() {
    if (loaded_value.value) return is_container(loaded_value.value.type);
    if (error.value) return false;
    if (!props.has_children) return false;
    return true;
});

function load() {
    if (!Number.isInteger(props.template_index)) {
        throw new TypeError('a template index must be an integer: ' + props.template_index);
    }

    if (props.template_index < 0) {
        throw new RangeError('a template index must not be negative: ' + props.template_index);
    }

    if (!Array.isArray(props.path)) {
        throw new TypeError('a value path must be a list: ' + String(props.path));
    }

    loading.value = true;
    error.value = null;

    const url = '/__kaleidoscope__/panels/templates/action/value/'
        + '?template=' + props.template_index
        + '&path=' + encodeURIComponent(JSON.stringify(props.path));

    fetch_native(url).then(function(response) {
        if (!response.ok) {
            return response.json().catch(function() { return {}; }).then(function(body: { error?: string }) {
                error.value = body.error ?? ('HTTP ' + response.status);
                loading.value = false;
            });
        }

        return response.json().then(function(data: { value: ValueData }) {
            loaded_value.value = data.value;
            loading.value = false;
        });
    }).catch(function(err: unknown) {
        error.value = String(err);
        loading.value = false;
    });
}

function toggle() {
    if (!can_expand.value) return;

    expanded.value = !expanded.value;

    if (expanded.value && loaded_value.value === null && !loading.value) {
        load();
    }
}

onMounted(function() {
    if (expanded.value && loaded_value.value === null && !loading.value) {
        load();
    }
});

function is_container(type: string): boolean {
    if (typeof type !== 'string') throw new TypeError('a value type must be text: ' + String(type));
    return CONTAINER_TYPES.includes(type);
}

function children_of(node: ValueData): ChildEntry[] {
    const attributed = node.type === 'object' || node.type === 'model';
    const children = (attributed ? node.attributes : node.items) ?? [];

    if (!Array.isArray(children)) {
        throw new TypeError('value children must be a list: ' + String(children));
    }

    return children;
}

function children_separator(node: ValueData): string {
    if (node.type === 'object' || node.type === 'model' || node.type === 'enum') return '=';
    return ':';
}

function container_header(node: ValueData): string {
    const name = node.class_name ?? '';
    const size = node.size ?? 0;
    if (!Number.isFinite(size)) throw new RangeError('a container size must be finite: ' + size);

    if (node.type === 'object') return '<' + name + '>';
    if (node.type === 'model') return '<' + name + ' pk=' + (node.pk ?? '') + '>';
    if (node.type === 'queryset') return '<QuerySet [' + (node.model ?? '') + '] size=' + size + '>';
    if (node.type === 'enum') return '<' + name + '[' + size + ']>';
    if (node.type === 'dict') return 'dict[' + size + ']';
    if (node.type === 'list') return 'list[' + size + ']';
    if (node.type === 'tuple') return 'tuple[' + size + ']';
    if (node.type === 'set') return 'set[' + size + ']';
    return '';
}

function code_for_leaf(node: ValueData): string {
    if (node.type === 'none') return 'None';
    if (node.type === 'bool') return node.value ? 'True' : 'False';
    if (node.type === 'number') return node.repr ?? '';

    if (node.type === 'string') {
        const raw = typeof node.value === 'string' ? node.value : '';
        const quoted = JSON.stringify(raw);
        const inner = quoted.slice(1, -1).replace(/'/g, "\\'");
        let code = "'" + inner + "'";

        if (node.truncated) {
            code += '  # ...+' + node.truncated + ' chars';
        }

        return code;
    }

    if (node.type === 'lazy') return '<lazy>';
    if (node.type === 'callable') return '<fn ' + (node.name ?? '') + '>';

    if (node.type === 'repr') {
        let code = typeof node.value === 'string' ? node.value : '';

        if (node.truncated) {
            code += '  # ...+' + node.truncated + ' chars';
        }

        return code;
    }

    if (node.type === 'error') return '<' + (node.class_name ?? '') + ' error>';

    return '';
}

function sub_path(step: PathStep): PathStep[] {
    const value: unknown = step;

    if (typeof value !== 'object') {
        throw new TypeError('a path step must be a record, not ' + typeof value);
    }

    if (value === null) throw new TypeError('a path step must be a record, not null');

    if (typeof step.kind !== 'string') {
        throw new TypeError('a path step kind must be text: ' + String(step.kind));
    }

    return [...props.path, step];
}
</script>

<template>
    <div>
        <div
            class="flex items-baseline gap-1.5 px-1 py-0.5 rounded-sm leading-5"
            :class="[can_expand ? 'hover:bg-white/3 cursor-pointer' : '']"
            @click="toggle"
        >
            <span class="w-3 shrink-0 inline-flex items-center justify-center self-center">
                <ChevronRight
                    v-if="can_expand"
                    :size="12"
                    class="opacity-40 transition-transform"
                    :class="expanded ? 'rotate-90' : ''"
                />
            </span>

            <span v-if="label" class="font-mono text-[12px] text-blue-300 shrink-0 leading-5">{{ label }}</span>
            <span v-if="label && separator" class="text-gray-500 text-[12px] shrink-0 leading-5">{{ separator }}</span>
            <span class="flex-1 min-w-0 leading-5 inline-block">
                <PrismCode v-if="loaded_value && is_container(loaded_value.type) && expanded" :code="container_header(loaded_value)" />
                <PrismCode v-else-if="loaded_value && !is_container(loaded_value.type)" :code="code_for_leaf(loaded_value)" />
                <PrismCode v-else-if="preview" :code="preview" />
            </span>
        </div>

        <div v-if="expanded" class="pl-4">
            <div v-if="loading" class="text-[11px] opacity-40 italic px-1 py-0.5 leading-5">Loading...</div>
            <div v-else-if="error" class="text-[12px] text-red-400 px-1 py-0.5 leading-5">Error: {{ error }}</div>
            <template v-else-if="loaded_value">
                <div v-if="loaded_value.error" class="text-[12px] text-red-400 px-1 py-0.5 leading-5">
                    QuerySet error: {{ loaded_value.error }}
                </div>
                <template v-if="is_container(loaded_value.type)">
                    <ValueNode
                        v-for="(child, i) in children_of(loaded_value)"
                        :key="i"
                        :template_index="template_index"
                        :path="sub_path(child.step)"
                        :label="child.label"
                        :preview="child.preview"
                        :has_children="child.has_children"
                        :separator="children_separator(loaded_value)"
                        :depth="(depth || 0) + 1"
                    />
                    <div v-if="loaded_value.truncated" class="text-[11px] opacity-30 italic px-1 py-0.5 leading-5">
                        ... {{ loaded_value.truncated }} more
                    </div>
                </template>
            </template>
        </div>
    </div>
</template>
