/*
 * The v1 tree: its own providers and routes, never inside a v0 layout or
 * guard. Loaded lazily by the version switch, so v1's code reaches the
 * browser only when a v1 page renders; its styles are in the global
 * stylesheet (vite.config.js sets cssCodeSplit: false). The Toaster mounts
 * here, once, so `notify()` reaches the user on every v1 page, and so do the
 * one QueryClient and the plugin slots. Each page renders behind its
 * session guard (`app/session/`); the shell (P2-T01) mounts here.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "@v1/app/query";
import type { RegistryEntry } from "@v1/app/registry/types";
import { RouteGate } from "@v1/app/session/RouteGate";
import { ThemeProvider } from "@v1/app/theme/ThemeProvider";
import { Toaster } from "@v1/components/ui/feedback";
import { PluginProvider } from "@v1/lib/plugins";
import { PluginSlot } from "@v1/plugins";
import { onSessionExpired } from "@v1/services/context";
import { signOutAndLeave } from "@v1/services/session";
import { type JSX, Suspense, useEffect } from "react";
import { Route, Routes } from "react-router-dom";
import { PAGE_COMPONENTS } from "./pages";

export type V1AppProps = Readonly<{ entry: RegistryEntry }>;

/** One cache for the v1 tree, kept across v1 pages; exported so tests can clear it. */
export const v1QueryClient = createQueryClient();

export function V1App({ entry }: V1AppProps): JSX.Element {
  // An expired session signs out as v0 does, and lands where v0's logout does.
  useEffect(() => onSessionExpired(signOutAndLeave), []);
  const Page = PAGE_COMPONENTS[entry.page];
  if (!Page) {
    throw new Error(`v1 page ${entry.page} is registered but has no component`);
  }
  const page = (
    <RouteGate access={entry.access}>
      <Page />
    </RouteGate>
  );
  return (
    <QueryClientProvider client={v1QueryClient}>
      <ThemeProvider>
        <PluginProvider slot={PluginSlot}>
          <Suspense fallback={null}>
            <Routes>
              {entry.v1Routes.map((path) => (
                <Route key={path} path={path} element={page} />
              ))}
            </Routes>
          </Suspense>
        </PluginProvider>
        <Toaster />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
