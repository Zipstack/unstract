import fs from "fs";
import path from "path";

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
export function optionalPluginImports() {
  return {
    name: "optional-plugin-imports",
    resolveId(source, importer) {
      if (!importer) {
        return null;
      }

      // Only handle relative imports
      if (!source.startsWith(".")) {
        return null;
      }

      // Strip query strings and hashes (e.g. "./logo.svg?react" → "./logo.svg")
      // so path.extname and fs.existsSync work correctly.
      const sourcePath = source.split("?")[0].split("#")[0];
      const resolved = path.resolve(path.dirname(importer), sourcePath);

      // Only handle imports that resolve within a plugins directory.
      // This covers both cross-plugin imports (e.g. "../plugins/foo")
      // and intra-plugin sibling imports (e.g. "./TrialMessage" from
      // within plugins/login-form/).
      if (!resolved.includes("/plugins/")) {
        return null;
      }

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
