import path from "path";
import { fileURLToPath } from "url";
import { defineConfig, transformWithEsbuild } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  plugins: [
    svgr({
      exportAsDefault: false,
      svgrOptions: {
        exportType: "named",
        namedExport: "ReactComponent",
      },
      include: "**/*.svg", // <-- this makes it apply globally
    }),
    react(),

    // 👇 Add this plugin to treat .js as JSX
    {
      name: "load-js-as-jsx",
      async transform(code, id) {
        if (id.endsWith(".js") && id.includes("/src/")) {
          return transformWithEsbuild(code, id, {
            loader: "jsx",
            jsx: "automatic",
          });
        }
        return null;
      },
    },
  ],

  optimizeDeps: {
    esbuildOptions: {
      loader: {
        ".js": "jsx",
      },
    },
  },

  server: {
    port: 3000,
    strictPort: true,
    fs: {
      allow: [".."],
    },
  },

  resolve: {
    alias: {
      "@manual-review": path.resolve(
        __dirname,
        "../unstract-cloud/frontend/src/plugins/manual-review"
      ),
    },
  },
});
