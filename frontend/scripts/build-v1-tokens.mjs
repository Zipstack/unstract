import fs from "node:fs";
import { registerHooks } from "node:module";
import path from "node:path";

// Node's ESM resolver needs file extensions; v1 source imports siblings without
// them (`./theme`), as Vite and tsc expect. Retry such relative imports as `.ts`.
registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (error) {
      if (specifier.startsWith(".") && !path.extname(specifier)) {
        return nextResolve(`${specifier}.ts`, context);
      }
      throw error;
    }
  },
});

const { renderTokensCss } = await import("../src/v1/lib/tokens.ts");
const { TOKENS } = await import("../src/v1/styles/tokens.ts");
const out = path.join(
  import.meta.dirname,
  "..",
  "src",
  "v1",
  "styles",
  "tokens.css",
);
const css = renderTokensCss(TOKENS);
if (process.argv.includes("--check")) {
  if (fs.readFileSync(out, "utf8") !== css) {
    console.error(
      "src/v1/styles/tokens.css is stale; run `bun run tokens:v1`.",
    );
    process.exit(1);
  }
} else {
  fs.writeFileSync(out, css);
}
