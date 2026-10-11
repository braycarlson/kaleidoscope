import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

function chunk_file_name(chunk_info) {
    if (chunk_info.name) {
        if (chunk_info.name !== 'index') {
            return 'kaleidoscope-' + chunk_info.name + '.js';
        }
    }

    const modules = Object.keys(chunk_info.modules || {});

    for (const module_path of modules) {
        if (module_path.includes('sql-formatter')) {
            return 'kaleidoscope-sql-formatter.js';
        }
    }

    return 'kaleidoscope-[name].js';
}

function chunk_manual(id) {
    if (id.includes('node_modules/sql-formatter')) {
        return 'sql-formatter';
    }

    return undefined;
}

export default defineConfig({
    plugins: [vue()],
    build: {
        outDir: '../static/kaleidoscope',
        emptyOutDir: true,
        rollupOptions: {
            input: 'src/main.ts',
            output: {
                entryFileNames: 'kaleidoscope.js',
                chunkFileNames: chunk_file_name,
                assetFileNames: 'kaleidoscope.[ext]',
                manualChunks: chunk_manual,
            },
        },
    },
});
