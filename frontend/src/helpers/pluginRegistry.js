import { lazy } from "react";

import { NotFound } from "../components/error/NotFound/NotFound.jsx";

// The only error that means "this plugin was not shipped" is the build-time
// stub vite.config.js's `optionalPluginImports` resolves a missing optional
// plugin to: `throw new Error('Optional plugin not available')`. We match that
// exact signal and nothing else.
//
// We deliberately do NOT reuse the broader `isModuleMissing` here: it also
// matches "Failed to fetch dynamically imported module", which is a TRANSIENT
// chunk-load failure of a plugin that IS shipped (CDN/origin blip, stale hashed
// asset). Treating that as "absent" would silently render NotFound for a real,
// momentarily-unreachable route instead of surfacing the failure.
function isPluginAbsent(err) {
  return (err?.message || "").includes("Optional plugin not available");
}

// Wrap an enterprise plugin's dynamic import as a lazy route element. The
// plugin chunk is fetched only when the element actually renders (i.e. on
// navigation to its route), so plugins are never pulled onto the
// unauthenticated /landing page — which is the whole point of this change.
//
// The import thunk is written at the call site so the literal `../plugins/...`
// path stays statically analyzable: only entrypoints a route actually
// references enter the build graph (an unreferenced/broken plugin file can't
// fail the build), and vite.config.js's `optionalPluginImports` can resolve
// the path to its stub in OSS builds.
//
// Registration is unconditional. In OSS the stub makes the import reject, which
// we map to the app's NotFound page so the route harmlessly 404s — the same
// user-visible result as the previous "route not registered" branch. Any other
// failure (incl. a transient chunk-load error of a shipped plugin) is re-thrown
// so it surfaces instead of being silently swallowed.
export function lazyPlugin(loader, exportName = "default") {
  return lazy(() =>
    loader()
      .then((m) => {
        const component = m[exportName] ?? m.default;
        if (!component) {
          // The plugin loaded but the expected export is gone (renamed/
          // removed). Fail loudly with the offending name instead of handing
          // React.lazy `{ default: undefined }`. isPluginAbsent won't match
          // this message, so it re-throws to the ErrorBoundary rather than
          // masquerading as an absent plugin.
          throw new Error(
            `lazyPlugin: module loaded but has no export "${exportName}" (or default)`,
          );
        }
        return { default: component };
      })
      .catch((err) => {
        if (isPluginAbsent(err)) {
          return { default: NotFound };
        }
        throw err;
      }),
  );
}
