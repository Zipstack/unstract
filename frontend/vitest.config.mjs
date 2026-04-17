import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react({
      include: "**/*.{jsx,js}",
    }),
  ],
  esbuild: {
    loader: "jsx",
    include: /src\/.*\.jsx?$/,
  },
  test: {
    globals: true,
    environment: "happy-dom",
    setupFiles: "./src/setupTests.js",
  },
});
