import { lazy } from "react";

// Lazy-load a module's NAMED export as a route component. React.lazy expects a
// module with a `default` export, so this adapts `{ Foo }` to `{ default: Foo }`.
// Use it to code-split route pages/layouts that use named exports without
// repeating the `.then((m) => ({ default: m.X }))` boilerplate at every site.
//
// For DEFAULT-exported components, use `lazy(() => import(...))` directly.
// For OPTIONAL enterprise plugins that may be absent in OSS, use `lazyPlugin`
// (pluginRegistry.js) instead — it adds the missing-plugin NotFound fallback.
export function lazyNamed(loader, exportName) {
  return lazy(() => loader().then((m) => ({ default: m[exportName] })));
}
