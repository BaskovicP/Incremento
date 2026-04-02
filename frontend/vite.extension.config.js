import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "../chrome_extensions/incremento_companion/dist",
    emptyOutDir: true,
    minify: true,
    sourcemap: false,
    rollupOptions: {
      input: {
        popup: "../chrome_extensions/incremento_companion/src/popup/main.jsx",
        bookmarks: "../chrome_extensions/incremento_companion/src/bookmarks/main.jsx",
        background: "../chrome_extensions/incremento_companion/src/background/main.js",
        content: "../chrome_extensions/incremento_companion/src/content/main.js",
        offscreen: "../chrome_extensions/incremento_companion/src/offscreen/main.js",
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
        manualChunks(id) {
          if (id.includes("node_modules")) {
            return "extension-vendor";
          }
          if (id.includes("chrome_extensions/incremento_companion/src/shared/")) {
            return "extension-shared";
          }
          return null;
        },
      },
    },
  },
});
