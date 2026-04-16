<script setup lang="ts">
interface Stat {
    label: string;
    value: string | number;
}

defineProps<{
    stats: Stat[];
}>();
</script>

<template>
    <div class="flex flex-wrap items-center gap-3 sm:gap-7 pb-4 mb-6 border-b border-white/[0.08]">
        <div v-for="stat in stats" :key="stat.label" class="flex items-center gap-2">
            <span class="opacity-40 text-[13px]">{{ stat.label }}</span>
            <span class="font-semibold text-[13px]">{{ stat.value }}</span>
        </div>

        <slot />
    </div>
</template>
