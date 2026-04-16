import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
    plugins: [vue()],
    build: {
        outDir: '../static/kaleidoscope',
        emptyOutDir: true,
        rollupOptions: {
            input: 'src/main.ts',
            output: {
                entryFileNames: 'kaleidoscope.js',
                assetFileNames: 'kaleidoscope.[ext]',
                inlineDynamicImports: true,
            },
        },
    },
});
