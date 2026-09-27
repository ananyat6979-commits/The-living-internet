import { defineConfig } from "vitest/config";

// GitHub Pages serves project sites from /<repo>/. The workflow sets BASE_PATH; locally it is "/".
export default defineConfig({
  base: process.env.BASE_PATH ?? "/",
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 300 },
  test: { environment: "jsdom", globalSetup: ["src/test/globalSetup.ts"] },
});
