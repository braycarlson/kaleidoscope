<script setup lang="ts">
import { computed } from 'vue';
import Prism from 'prismjs';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-sql';

const props = withDefaults(defineProps<{
    code: string;
    language?: string;
    block?: boolean;
}>(), {
    language: 'python',
    block: false,
});

function escape_html(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

const html = computed(function() {
    const grammar = Prism.languages[props.language];

    if (!grammar) {
        return escape_html(props.code);
    }

    try {
        return Prism.highlight(props.code, grammar, props.language);
    } catch {
        return escape_html(props.code);
    }
});
</script>

<template>
    <pre
        v-if="block"
        class="ks-code-block font-mono text-[12px] leading-5 whitespace-pre overflow-x-auto p-3 rounded border border-white/[0.06] bg-black/30"
    ><code v-html="html" /></pre>
    <span
        v-else
        class="font-mono text-[12px] whitespace-pre-wrap break-all leading-5 align-baseline"
        v-html="html"
    />
</template>
