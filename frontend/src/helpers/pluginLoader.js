// The one way to load an optional enterprise plugin that may be absent (OSS
// builds ship without `src/plugins/`). Route elements use `lazyPlugin`
// (pluginRegistry.js); everything else — components, hooks, stores, helpers,
// constants — goes through `loadPlugin`.
//
// Zero-dependency on purpose: consumers include modules that import each
// other (Router/useMainAppRoutes/PageLayout), and this helper must never
// re-introduce an import cycle.

// The only error that means "this plugin was not shipped" is the build-time
// stub vite.config.js's `optionalPluginImports` resolves a missing optional
// plugin to: `throw new Error('Optional plugin not available')`.
// `MODULE_NOT_FOUND` / "Cannot find module" are the Node equivalents, kept for
// anything that loads these modules outside Vite.
//
// "Failed to fetch dynamically imported module" is deliberately NOT here: it
// is a plugin that IS shipped but whose chunk failed to load (CDN/origin
// blip, stale hashed asset, or a syntax error the dev server refused to
// serve). That is a real failure and must be logged, not mistaken for absence.
export function isPluginAbsent(err) {
  const msg = err?.message || "";
  return (
    msg.includes("Optional plugin not available") ||
    err?.code === "MODULE_NOT_FOUND" ||
    msg.includes("Cannot find module")
  );
}

// Load an optional plugin, resolving to `fallback` when it is unavailable.
//
//   const TrialDaysInfo = await loadPlugin(() =>
//     import("../plugins/x/TrialDaysInfo.jsx").then((m) => m.default),
//   );
//
// - `importer` is a thunk so the literal `../plugins/...` path stays at the
//   call site, where Vite can statically resolve it (and stub it in OSS).
//   Have it return exactly the value you need — pick the export in `.then`.
// - Resolves to `fallback` when the plugin is absent, when the import fails
//   for any other reason, or when the importer yields `undefined`/`null`
//   (e.g. the export was renamed, or vitest's empty stub module).
// - Absence is the expected OSS case and stays silent. Every other failure is
//   logged here, so a broken plugin is never indistinguishable from a
//   missing one.
//
// Load ONE plugin module per call: sharing a call (or a try block) between
// plugins lets one missing plugin disable the others.
export async function loadPlugin(importer, fallback = null) {
  try {
    return (await importer()) ?? fallback;
  } catch (err) {
    if (!isPluginAbsent(err)) {
      reportPluginLoadError(err);
    }
    return fallback;
  }
}

function reportPluginLoadError(err) {
  console.error("[plugin] failed to load; using the fallback instead", err);
}
