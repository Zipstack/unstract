import { lazy } from "react";

import { NotFound } from "../components/error/NotFound/NotFound.jsx";
import { isModuleMissing } from "./pluginLoader.js";

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
// Registration is unconditional. In OSS the stub makes the import reject with
// a missing-module error, which we map to the app's NotFound page so the route
// harmlessly 404s — the same user-visible result as the previous "route not
// registered" branch. A plugin that is present but throws for any OTHER reason
// is re-thrown so the failure is loud instead of silently swallowed.
export function lazyPlugin(loader, exportName = "default") {
  return lazy(() =>
    loader()
      .then((m) => ({ default: m[exportName] ?? m.default }))
      .catch((err) => {
        if (isModuleMissing(err)) {
          return { default: NotFound };
        }
        throw err;
      }),
  );
}
