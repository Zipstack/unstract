import fs from "node:fs";
import path from "node:path";

// Runs under bun (`bun run tokens:v1`): it imports the TypeScript sources
// directly and resolves extensionless relative imports (`./theme`) as Vite and
// tsc do. Node would need a resolver hook and Node 22.15+ for it; the engines
// field allows 20.19, so the generator does not use node.

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
