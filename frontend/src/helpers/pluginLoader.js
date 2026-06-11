// Classify a dynamic plugin-import failure as "plugin not shipped"
// (expected in OSS builds) vs. a real load failure.
//
// LIMITATION: in a browser/Vite bundle this isn't fully sound — a
// genuinely-absent plugin and a present-but-failed-to-load chunk
// (transient CDN/origin 5xx, a stale hashed asset) both surface as
// "Failed to fetch dynamically imported module", and `MODULE_NOT_FOUND`
// is a Node/CJS code that only appears under jsdom/vitest, not the
// shipped bundle. So a transient chunk-load failure can be misread as
// "missing" and de-register the route for that session — same outcome
// as a bare `catch`, but genuine errors in the present-plugin case at
// least get logged. Centralized so any future hardening lands once.
//
// Zero-dependency on purpose: consumers include modules that import
// each other (Router/useMainAppRoutes/PageLayout), and this helper
// must never re-introduce an import cycle.
export function isModuleMissing(err) {
  const msg = err?.message || "";
  return (
    err?.code === "MODULE_NOT_FOUND" ||
    msg.includes("Failed to fetch dynamically imported module") ||
    msg.includes("Cannot find module")
  );
}
