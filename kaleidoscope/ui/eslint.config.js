import js from '@eslint/js';
import globals from 'globals';
import ts from 'typescript-eslint';
import vue from 'eslint-plugin-vue';

export default ts.config(
    {
        ignores: ['coverage/'],
    },
    js.configs.recommended,
    ...ts.configs.strictTypeChecked,
    ...ts.configs.stylisticTypeChecked,
    ...vue.configs['flat/recommended'],
    {
        languageOptions: {
            globals: globals.browser,
            parserOptions: {
                extraFileExtensions: ['.vue'],
                projectService: true,
                tsconfigRootDir: import.meta.dirname,
            },
        },
        rules: {
            'prefer-const': 'error',

            'no-unused-vars': 'off',
            '@typescript-eslint/no-unused-vars': ['error', {
                argsIgnorePattern: '^_',
            }],

            '@typescript-eslint/restrict-plus-operands': ['error', {
                allowNumberAndString: true,
            }],

            '@typescript-eslint/restrict-template-expressions': ['error', {
                allowNumber: true,
            }],

            'vue/attribute-hyphenation': 'off',
            'vue/html-indent': ['warn', 4],
            'vue/max-attributes-per-line': 'off',
            'vue/multi-word-component-names': 'off',
            'vue/prop-name-casing': 'off',
            'vue/require-default-prop': 'off',
            'vue/script-indent': ['warn', 4],
            'vue/singleline-html-element-content-newline': 'off',
        },
    },
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
        files: [
            'src/composables/use_interceptors.ts',
            'tests/composables/use_interceptors.test.ts',
        ],
        rules: {
            '@typescript-eslint/unbound-method': 'off',
        },
    },
    {
        files: ['tests/composables/use_panels.test.ts'],
        rules: {
            '@typescript-eslint/prefer-promise-reject-errors': 'off',
        },
    },
    {
        files: ['src/services/clipboard.ts'],
        rules: {
            '@typescript-eslint/no-deprecated': 'off',
        },
    },
    {
        files: ['**/*.js'],
        ...ts.configs.disableTypeChecked,
        languageOptions: {
            ...ts.configs.disableTypeChecked.languageOptions,
            globals: globals.node,
        },
    },
);
