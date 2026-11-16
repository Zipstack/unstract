/*
 * The v1 tree: its own providers and routes, never inside a v0 layout or
 * guard. Loaded lazily by the version switch, so v1's code reaches the
 * browser only when a v1 page renders; its styles are in the global
 * stylesheet (vite.config.js sets cssCodeSplit: false). The Toaster mounts
 * here, once, so `notify()` reaches the user on every v1 page. Session,
 * guards (P0-T06) and the shell (P2-T01) mount here.
 */

import type { RegistryEntry } from "@v1/app/registry/types";
import { ThemeProvider } from "@v1/app/theme/ThemeProvider";
import { Toaster } from "@v1/components/ui/feedback";
import { type JSX, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { PAGE_COMPONENTS } from "./pages";

export type V1AppProps = Readonly<{ entry: RegistryEntry }>;

export function V1App({ entry }: V1AppProps): JSX.Element {
  const Page = PAGE_COMPONENTS[entry.page];
  if (!Page) {
    throw new Error(`v1 page ${entry.page} is registered but has no component`);
  }
  return (
    <ThemeProvider>
      <Suspense fallback={null}>
        <Routes>
          {entry.v1Routes.map((path) => (
            <Route key={path} path={path} element={<Page />} />
          ))}
        </Routes>
      </Suspense>
      <Toaster />
    </ThemeProvider>
  );
}
