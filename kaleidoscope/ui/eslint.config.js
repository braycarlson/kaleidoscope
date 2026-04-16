import js from '@eslint/js';
import ts from 'typescript-eslint';
import vue from 'eslint-plugin-vue';

export default ts.config(
    js.configs.recommended,
    ...ts.configs.strict,
    ...vue.configs['flat/recommended'],
    {
        files: ['src/**/*.vue'],
        languageOptions: {
            parserOptions: {
                parser: ts.parser,
            },
        },
    },
    {
        files: ['src/env.d.ts'],
        rules: {
            '@typescript-eslint/no-explicit-any': 'off',
            '@typescript-eslint/no-empty-object-type': 'off',
        },
    },
    {
        languageOptions: {
            globals: {
                clearTimeout: 'readonly',
                console: 'readonly',
                document: 'readonly',
                Document: 'readonly',
                DragEvent: 'readonly',
                localStorage: 'readonly',
                MouseEvent: 'readonly',
                navigator: 'readonly',
                RequestInfo: 'readonly',
                RequestInit: 'readonly',
                setTimeout: 'readonly',
                TouchEvent: 'readonly',
                URL: 'readonly',
                window: 'readonly',
                XMLHttpRequest: 'readonly',
                XMLHttpRequestBodyInit: 'readonly',
            },
        },
        rules: {
            'prefer-const': 'error',

            'no-unused-vars': 'off',
            '@typescript-eslint/no-unused-vars': ['error', {
                argsIgnorePattern: '^_',
            }],

            'vue/attribute-hyphenation': 'off',
            'vue/html-indent': ['warn', 4],
            'vue/max-attributes-per-line': 'off',
            'vue/multi-word-component-names': 'off',
            'vue/prop-name-casing': 'off',
            'vue/script-indent': ['warn', 4],
            'vue/singleline-html-element-content-newline': 'off',
        },
    },
);
