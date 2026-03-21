import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    outDir: '../user_files/dist',
    emptyOutDir: true,
    lib: {
      entry: 'src/main.jsx',
      name: 'IncrementoPdfViewer',
      formats: ['iife'],
      fileName: () => 'pdf_viewer.js',
    },
    rollupOptions: {
      external: [],
    },
    minify: true,
    sourcemap: false,
  },
});
