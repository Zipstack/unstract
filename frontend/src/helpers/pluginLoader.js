// Classify a dynamic plugin-import failure as "plugin not shipped"
// (expected in OSS builds) vs. a real load failure.
//
// The PRIMARY signal in the shipped Vite bundle: vite.config.js's
// `optionalPluginImports` plugin resolves a missing optional-plugin path
// to a stub module whose body is `throw new Error('Optional plugin not
// available')`. That is the actual error an absent plugin throws in
// production, so it must be matched here or every OSS page load misfires
// the consumer's error branch.
//
// LIMITATION: this still isn't fully sound — a present-but-failed-to-load
// chunk (transient CDN/origin 5xx, a stale hashed asset) surfaces as
// "Failed to fetch dynamically imported module", and `MODULE_NOT_FOUND`
// is a Node/CJS code that only appears under jsdom/vitest, not the
// shipped bundle. So a transient chunk-load failure can be misread as
// "missing" and silently disable whatever the consumer gates on it —
// a route in the routers, the status banner in PageLayout — for that
// session. Same outcome as a bare `catch`, but genuine errors in the
// present-plugin case at least get logged. Centralized so any future
// hardening lands once.
//
// Zero-dependency on purpose: consumers include modules that import
// each other (Router/useMainAppRoutes/PageLayout), and this helper
// must never re-introduce an import cycle.
export function isModuleMissing(err) {
  const msg = err?.message || "";
  return (
    err?.code === "MODULE_NOT_FOUND" ||
    msg.includes("Optional plugin not available") ||
    msg.includes("Failed to fetch dynamically imported module") ||
    msg.includes("Cannot find module")
  );
}
