<script setup lang="ts">
import { Search } from 'lucide-vue-next';

withDefaults(defineProps<{
    placeholder?: string;
}>(), {
    placeholder: 'Filter...',
});

const model = defineModel<string>({ default: '' });
</script>

<template>
    <div class="w-full sm:w-auto relative flex items-center">
        <Search :size="14" class="absolute left-2.5 text-ks-faint" />
        <input
            v-model="model"
            type="text"
            :placeholder="placeholder"
            class="pl-8 pr-3 py-1 bg-ks-input border border-ks rounded text-[13px] outline-none focus:border-purple-500/50 w-full sm:w-56"
        >
    </div>
</template>
