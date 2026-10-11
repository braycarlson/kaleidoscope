<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ChevronRight, ExternalLink } from 'lucide-vue-next';
import CopyButton from '../CopyButton.vue';
import PanelHeader from '../PanelHeader.vue';

interface ProfilingPanelData {
    duration_ms?: number;
    error?: string;
    html?: string;
    text?: string;
}

const props = defineProps<{
    data: ProfilingPanelData;
}>();

const show_profile = ref(true);
const iframe_loaded = ref(false);

const stats = computed(function() {
    const duration_ms = props.data.duration_ms ?? 0;

    if (!Number.isFinite(duration_ms)) {
        throw new RangeError('a profile duration must be a finite number: ' + duration_ms);
    }

    return [{ label: 'Duration', value: duration_ms + ' ms' }];
});

watch(function() { return props.data.html; }, function() {
    iframe_loaded.value = false;
});

function toggle_profile() {
    show_profile.value = !show_profile.value;
}

function on_iframe_load(event: unknown) {
    const iframe = (event as { target: { contentDocument: Document | null } }).target;

    try {
        const doc = iframe.contentDocument;

        if (doc) {
            void doc.fonts.ready.then(function() {
                setTimeout(function() {
                    iframe_loaded.value = true;
                }, 300);
            });

            return;
        }
    } catch {
        // cross-origin
    }

    setTimeout(function() {
        iframe_loaded.value = true;
    }, 500);
}
</script>

<template>
    <div class="flex flex-col flex-1 min-h-0">
        <div v-if="data.error" class="py-10 text-center text-red-400 italic">{{ data.error }}</div>

        <template v-else>
            <PanelHeader :stats="stats">
                <a
                    v-if="data.html"
                    href="/__kaleidoscope__/panels/profiling/action/html/"
                    target="_blank"
                    class="ml-auto flex items-center gap-1 text-purple-400 font-semibold text-[13px] hover:underline"
                >
                    <ExternalLink :size="13" />
                    Open in New Tab
                </a>
            </PanelHeader>

            <template v-if="data.text">
                <div class="flex items-center gap-3 mb-3 shrink-0">
                    <div
                        class="font-semibold text-[13px] cursor-pointer select-none flex items-center gap-2 hover:opacity-80"
                        @click="toggle_profile"
                    >
                        <ChevronRight
                            :size="14"
                            class="opacity-40 transition-transform duration-150"
                            :class="show_profile ? 'rotate-90' : ''"
                        />
                        Profile
                    </div>
                    <CopyButton :value="data.text" />
                </div>

                <div v-show="show_profile" class="flex-1 min-h-0 relative">
                    <Transition
                        leave-active-class="transition-opacity duration-150 ease-in-out"
                        leave-to-class="opacity-0"
                    >
                        <div
                            v-if="!iframe_loaded"
                            class="absolute inset-0 z-10 flex items-center justify-center rounded-sm border border-white/6 bg-[#12121e]"
                        >
                            <span class="text-[13px] opacity-30 italic">Loading profile...</span>
                        </div>
                    </Transition>

                    <iframe
                        v-if="data.html"
                        src="/__kaleidoscope__/panels/profiling/action/html/"
                        class="w-full h-full rounded-sm border border-white/6 bg-white"
                        @load="on_iframe_load"
                    />
                </div>
            </template>

            <div v-if="!data.text && !data.html" class="py-10 text-center opacity-30 italic">No profile captured yet. Enable the panel, then navigate to a page.</div>
        </template>
    </div>
</template>
