import path from "node:path";

// vendor/cjs-lib stands in for a CommonJS package: Rollup reaches it through a
// virtual "\0…?commonjs-…" module, the edge the guard must follow.
export default {
  resolve: { alias: { "@v1": path.resolve(import.meta.dirname, "src/v1") } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    commonjsOptions: { include: [/vendor\/cjs-lib\//, /src\/legacy\.cjs$/] },
  },
};
