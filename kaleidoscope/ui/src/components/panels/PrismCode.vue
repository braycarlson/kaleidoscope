<script setup lang="ts">
import { computed, h, type VNode } from 'vue';
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

type Token = string | { type: string; content: Token | Token[]; alias?: string | string[] };

const TOKEN_DEPTH_MAX = 32;

function render_token(token: Token, depth: number): VNode | string {
    if (typeof token === 'string') return token;

    if (depth >= TOKEN_DEPTH_MAX) {
        throw new Error('the token tree is deeper than TOKEN_DEPTH_MAX');
    }

    const classes = ['token', token.type];

    if (token.alias) {
        if (Array.isArray(token.alias)) {
            classes.push(...token.alias);
        } else {
            classes.push(token.alias);
        }
    }

    const children = Array.isArray(token.content)
        ? token.content.map(function(child) { return render_token(child, depth + 1); })
        : [render_token(token.content, depth + 1)];

    return h('span', { class: classes.join(' ') }, children);
}

const nodes = computed(function(): (VNode | string)[] {
    if (typeof props.code !== 'string') {
        throw new TypeError('highlighted code must be text: ' + String(props.code));
    }

    const grammar = Prism.languages[props.language];

    if (!grammar) return [props.code];

    try {
        const tokens = Prism.tokenize(props.code, grammar) as Token[];
        return tokens.map(function(token) { return render_token(token, 0); });
    } catch {
        return [props.code];
    }
});

const Highlighted = computed(function() {
    if (props.block) {
        return h('pre', {
            class: 'ks-code-block font-mono text-[12px] leading-5 whitespace-pre overflow-x-auto p-3 rounded-sm border border-ks-section bg-ks-code',
        }, [h('code', {}, nodes.value)]);
    }

    return h('span', {
        class: 'font-mono text-[12px] whitespace-pre-wrap break-all leading-5 align-baseline',
    }, nodes.value);
});
</script>

<template>
    <component :is="Highlighted" />
</template>
