import path from "node:path";

export default {
  resolve: { alias: { "@v1": path.resolve(import.meta.dirname, "src/v1") } },
  build: { outDir: "dist", emptyOutDir: true },
};
