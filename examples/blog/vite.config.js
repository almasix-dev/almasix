import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";
import almasix from "./vite-plugin-almasix.js";

export default defineConfig({
  plugins: [almasix(), vue(), tailwindcss()],
  publicDir: false,
  build: {
    outDir: "public/build",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        app: resolve("resources/js/app.js"),
        css: resolve("resources/css/app.css"),
      },
    },
  },
  server: {
    origin: "http://127.0.0.1:5173",
  },
});
