import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import svgr from "vite-plugin-svgr";

import { optionalPluginImports } from "./vite-plugins/optional-plugin-imports";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [
      optionalPluginImports(),
      react({
        // Include .js files for JSX transformation
        include: "**/*.{jsx,js}",
      }),
      // SVG as React component support (for `import Logo from './logo.svg?react'`)
      svgr(),
    ],

    // ESBuild configuration to handle JSX in .js files
    esbuild: {
      loader: "jsx",
      include: /src\/.*\.jsx?$/,
      exclude: [],
    },

    // Resolve configuration
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },

    // Server configuration for development
    server: {
      host: "0.0.0.0",
      port: Number(env.PORT) || 3000,
      // Docker-specific: Enable polling for file watching
      watch: {
        usePolling: true,
        interval: 100,
      },
      // HMR configuration for Docker environments
      hmr: {
        port: Number(env.PORT) || 3000,
        clientPort: env.WDS_SOCKET_PORT
          ? Number(env.WDS_SOCKET_PORT)
          : Number(env.PORT) || 3000,
      },
      // Proxy configuration (similar to setupProxy.js in CRA)
      proxy:
        env.VITE_BACKEND_URL && env.VITE_BACKEND_URL.trim() !== ""
          ? {
              "/api": {
                target: env.VITE_BACKEND_URL,
                changeOrigin: true,
                secure: false,
              },
            }
          : undefined,
    },

    // Build configuration
    build: {
      target: "esnext",
      outDir: "build",
      sourcemap: true,
      // Single stylesheet: per-chunk CSS loads in navigation order, making
      // equal-specificity cross-component rules resolve unpredictably. JS
      // splitting is unaffected.
      cssCodeSplit: false,
      // Chunk size warning limit
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          // Manual chunk splitting for better caching
          manualChunks: {
            "react-vendor": ["react", "react-dom", "react-router-dom"],
            "antd-vendor": ["antd", "@ant-design/icons"],
            "pdf-vendor": [
              "@react-pdf-viewer/core",
              "@react-pdf-viewer/default-layout",
              "@react-pdf-viewer/highlight",
              "@react-pdf-viewer/page-navigation",
              "pdfjs-dist",
            ],
          },
        },
      },
    },

    // CSS configuration
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true,
        },
      },
    },

    // Define global constants
    define: {
      "process.env": {}, // For compatibility with some libraries expecting process.env
    },

    // Optimize dependencies
    optimizeDeps: {
      include: [
        "react",
        "react-dom",
        "react-router-dom",
        "antd",
        "@ant-design/icons",
      ],
      exclude: [],
      esbuildOptions: {
        loader: {
          ".js": "jsx",
        },
      },
    },
  };
});
