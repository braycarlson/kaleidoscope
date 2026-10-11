import { defineConfig, mergeConfig } from 'vitest/config';
import vite_config from './vite.config.js';

export default mergeConfig(vite_config, defineConfig({
    test: {
        coverage: {
            include: ['src/**/*.{ts,vue}'],
            provider: 'v8',
            reporter: ['text', 'html'],
            thresholds: {
                branches: 95,
                functions: 98,
                lines: 98,
                statements: 98,
            },
        },
        environment: 'jsdom',
        include: ['tests/**/*.test.ts'],
        restoreMocks: true,
        setupFiles: ['tests/support/setup.ts'],
        unstubGlobals: true,
    },
}));
