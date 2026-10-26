import { expect, it } from "vitest";

/*
 * v0's optionalPluginImports (vite.config.js, vitest.config.mjs) turns any
 * missing import under a `/plugins/` path into a stub. v1 has no optional
 * imports: an absent plugin has no manifest, so a missing module is a bug.
 * The specifier is a variable so the failure surfaces at run time, where the
 * test can see it; a literal one fails the transform, which is the same rule.
 */
it("a missing module under v1 fails to import instead of being stubbed", async () => {
  const missing = "./does-not-exist";
  await expect(import(/* @vite-ignore */ missing)).rejects.toThrow();
});
