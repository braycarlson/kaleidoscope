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
                chunkFileNames: function(chunkInfo) {
                    if (chunkInfo.name && chunkInfo.name !== 'index') {
                        return 'kaleidoscope-' + chunkInfo.name + '.js';
                    }

                    const modules = Object.keys(chunkInfo.modules || {});

                    for (const module_path of modules) {
                        if (module_path.includes('sql-formatter')) {
                            return 'kaleidoscope-sql-formatter.js';
                        }
                    }

                    return 'kaleidoscope-[name].js';
                },
                assetFileNames: 'kaleidoscope.[ext]',
                manualChunks: function(id) {
                    if (id.includes('node_modules/sql-formatter')) {
                        return 'sql-formatter';
                    }

                    return undefined;
                },
            },
        },
    },
});
