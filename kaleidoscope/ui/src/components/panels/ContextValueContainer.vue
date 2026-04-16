<script setup lang="ts">
import ValueNode from './ValueNode.vue';

defineProps<{
    template_index: number;
    active_key: string | null;
}>();
</script>

<template>
    <div v-if="active_key" class="mt-3 rounded border border-white/[0.06] h-80 overflow-auto">
        <Transition
            enter-active-class="transition-opacity duration-150 ease-out"
            leave-active-class="transition-opacity duration-100 ease-in"
            enter-from-class="opacity-0"
            leave-to-class="opacity-0"
            mode="out-in"
        >
            <div :key="template_index + ':' + active_key" class="p-3">
                <ValueNode
                    :template_index="template_index"
                    :path="[{ kind: 'key', name: active_key }]"
                    :label="active_key"
                    separator=":"
                    :auto_expand="true"
                />
            </div>
        </Transition>
    </div>
</template>
