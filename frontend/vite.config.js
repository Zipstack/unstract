import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";
import { defineConfig, loadEnv, transformWithEsbuild } from "vite";
import svgr from "vite-plugin-svgr";

const EMPTY_MODULE_ID = "\0optional-plugin-empty";
const EMPTY_ASSET_MODULE_ID = "\0optional-plugin-empty-asset";

const ASSET_EXTENSIONS = new Set([
  ".svg",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".ico",
  ".bmp",
  ".tiff",
]);

// Rollup plugin that resolves missing optional plugin imports to an empty
// module instead of failing the build.  This lets the existing
// `try { await import("./plugins/...") } catch {}` pattern work at build
// time: Rollup will bundle an empty module for any plugin path that does
// not exist on disk, and the catch block handles the rest at runtime.
//
// Asset imports (images, SVGs, etc.) are resolved to a module that exports
// an empty string as default, so static `import logo from "..."` statements
// don't break the build.
function optionalPluginImports() {
  return {
    name: "optional-plugin-imports",
    resolveId(source, importer) {
      if (!importer) return null;

      // Only handle relative imports
      if (!source.startsWith(".")) return null;

      // Strip query strings and hashes (e.g. "./logo.svg?react" → "./logo.svg")
      // so path.extname and fs.existsSync work correctly.
      const sourcePath = source.split("?")[0].split("#")[0];
      const resolved = path.resolve(path.dirname(importer), sourcePath);

      // Only handle imports that resolve within a plugins directory.
      // This covers both cross-plugin imports (e.g. "../plugins/foo")
      // and intra-plugin sibling imports (e.g. "./TrialMessage" from
      // within plugins/login-form/).
      if (!resolved.includes("/plugins/")) return null;

      // Check common extensions
      const extensions = ["", ".js", ".jsx", ".ts", ".tsx"];
      const exists = extensions.some(
        (ext) =>
          fs.existsSync(resolved + ext) ||
          fs.existsSync(path.join(resolved, "index" + (ext || ".js"))),
      );

      if (!exists) {
        // Asset files need a default export so static imports work.
        const ext = path.extname(sourcePath).toLowerCase();
        if (ASSET_EXTENSIONS.has(ext)) {
          return EMPTY_ASSET_MODULE_ID;
        }
        return EMPTY_MODULE_ID;
      }

      return null;
    },
    load(id) {
      if (id === EMPTY_MODULE_ID) {
        return "throw new Error('Optional plugin not available');";
      }
      if (id === EMPTY_ASSET_MODULE_ID) {
        return "export default '';";
      }
      return null;
    },
  };
}

/*
 * Transforms JSX that lives in plain `.js` files.
 *
 * This is NOT transitional. The OSS tree's own JSX-bearing `.js` files were
 * renamed to `.jsx`, but this build also compiles `src/plugins/`, which is
 * copied in from the separate unstract-cloud repo at Docker build time. Nine
 * of those plugin files put JSX in `.js`, and they are invisible from here —
 * the first sign of trouble is a Docker build failing with
 * "content contains invalid JS syntax".
 *
 * Deleting this to "clean up" therefore breaks the cloud image, not the OSS
 * one. Renaming the cloud files instead would impose an unwritten rule (no
 * JSX in `.js`, anywhere, ever) that nothing enforces and cloud developers
 * cannot see.
 *
 * Scoped to `.js` on purpose. Vite's own `esbuild` option cannot express this:
 * its `include` REPLACES the default filter, and its `loader` is one string
 * applied to every matched file, so covering `.js` there would hand `.ts` to
 * the JSX parser.
 */
function jsxInJs() {
  return {
    name: "jsx-in-js",
    async transform(code, id) {
      if (id.includes("/node_modules/")) {
        return null;
      }
      const [filepath] = id.split("?");
      if (!/\/src\/.*\.js$/.test(filepath)) {
        return null;
      }
      return transformWithEsbuild(code, filepath, {
        loader: "jsx",
        /*
         * `jsx: "automatic"` is load-bearing, and its absence does NOT fail
         * the build — it produces a white screen at runtime.
         *
         * esbuild defaults to the classic runtime, emitting
         * `React.createElement(...)`. These files use JSX without importing
         * React (the automatic runtime injects `jsx-runtime` itself), so the
         * classic output referenced an undefined binding and threw
         * `ReferenceError: React is not defined` while rendering the router —
         * killing the whole app, with a green build and HTTP 200 throughout.
         *
         * The old `esbuild` block never hit this because Vite applies its own
         * resolved `jsx` setting to that path; a standalone
         * transformWithEsbuild call does not inherit it.
         */
        jsx: "automatic",
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [
      optionalPluginImports(),
      // Tailwind v4. Must come after optionalPluginImports() so missing
      // cloud-plugin imports are still resolved to stubs first.
      tailwindcss(),
      // Must precede react(): it turns JSX-bearing .js into plain JS, which is
      // what the React transform (and Rollup's import analysis) then expect.
      jsxInJs(),
      react({
        // Include .js files for JSX transformation, plus the TypeScript
        // shim layer so it gets Fast Refresh in dev like everything else.
        include: "**/*.{jsx,js,tsx,ts}",
      }),
      // SVG as React component support (for `import Logo from './logo.svg?react'`)
      svgr(),
    ],

    /*
     * No `esbuild` override here, deliberately — Vite's defaults
     * (`include: /\.(m?ts|[jt]sx)$/`, and a loader derived per-file from the
     * extension) are exactly right once TypeScript is in the tree.
     *
     * This block previously read `{ loader: "jsx", include: /src\/.*\.jsx?$/ }`
     * to cope with .js files that contain JSX. Both halves break TypeScript,
     * and each cost a build to diagnose:
     *
     *   - `include` REPLACES Vite's default filter rather than extending it,
     *     so .ts/.tsx were never transformed at all and failed to parse with a
     *     bare "Expected ';', '}' or <eof>".
     *   - `loader` reaches esbuild's single-file transform API, where it must
     *     be a string (the per-extension map form is bundle-API only) and is
     *     applied to every matched file. One blanket "jsx" hands TypeScript to
     *     the JSX parser, which misreads the `<` in
     *     `React.forwardRef<HTMLButtonElement, Props>(…)` as an opening tag.
     *
     * JSX-in-.js is handled by jsxInJs() above instead — see the note there
     * for why the cloud plugin tree makes that a permanent requirement rather
     * than a transitional one.
     */

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
      // Vite refuses requests whose Host header is not localhost or an IP, as a
      // DNS-rebinding guard. That is the right default locally, but when the dev
      // server runs inside a cluster pod behind an ingress the browser sends the
      // real domain and every request comes back "Blocked request". Opt in per
      // environment with a comma-separated list, e.g. ".example.com".
      // Empty list == Vite's default (localhost/IPs only), so local dev and the
      // production build are unaffected.
      allowedHosts: env.VITE_DEV_ALLOWED_HOSTS
        ? env.VITE_DEV_ALLOWED_HOSTS.split(",")
            .map((host) => host.trim())
            .filter(Boolean)
        : [],
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
        // Behind a TLS-terminating ingress the page is served over https, so the
        // HMR socket has to be wss on the ingress port (443) rather than the
        // port the dev server itself listens on. Left unset, Vite derives the
        // protocol from its own (plain http) server and the socket never opens.
        ...(env.VITE_DEV_HMR_PROTOCOL
          ? { protocol: env.VITE_DEV_HMR_PROTOCOL }
          : {}),
      },
      // Proxy configuration (similar to setupProxy.js in CRA)
      proxy:
        env.VITE_BACKEND_URL && env.VITE_BACKEND_URL.trim() !== ""
          ? {
              "/api": {
                target: env.VITE_BACKEND_URL,
                changeOrigin: true,
                secure: false,
                // Forward WebSocket upgrades too — the Socket.IO log/result
                // channel connects to `/api/v1/socket` with a websocket-only
                // transport. Without this the upgrade is never proxied to the
                // backend and Prompt Studio results never stream to the UI in
                // dev. (Prod is unaffected: Traefik routes /api/v1/socket.)
                ws: true,
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

    // Define global constants
    define: {
      "process.env": {}, // For compatibility with some libraries expecting process.env
    },

    // Optimize dependencies
    optimizeDeps: {
      include: ["react", "react-dom", "react-router-dom"],
      exclude: [],
      esbuildOptions: {
        loader: {
          ".js": "jsx",
        },
      },
    },
  };
});
