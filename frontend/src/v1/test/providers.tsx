import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@v1/app/theme/ThemeProvider";
import { getPortalContainer, PORTAL_CONTAINER_ID } from "@v1/lib/portal";
import { THEME_STORAGE_KEY } from "@v1/lib/theme";
import { useThemeStore } from "@v1/stores/theme";
import type { JSX, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ThemeMode } from "./session";

/*
 * The v1 provider chain for tests: the ONLY file to edit when a real provider
 * lands. A slot is the app's own provider once its task has merged, and a
 * stand-in until then:
 *
 *   query   stand-in  P0-T05 data layer (UN-4313) → the app's QueryClient provider
 *   router  stand-in  P0-T03 router + registry (UN-4271) → the app's router, in memory
 *   theme   real      app/theme/ThemeProvider (P0-T04, #2399)
 *
 * Swap a slot by changing its entry in PROVIDER_SLOTS (and, if it holds
 * global state, prepareProviders / resetProviders); renderV1 and every test
 * stay as they are. See README.md in this folder.
 *
 * Every field here is read by a slot. A new one (a session, a distribution)
 * arrives together with the slot that reads it, never ahead of it.
 */

/** Everything a slot may need, resolved from renderV1's options. */
export type ProviderContext = Readonly<{
  queryClient: QueryClient;
  /** The URL the router starts at. */
  route: string;
  /** A route pattern to mount the UI under, so `useParams` resolves. */
  path: string | undefined;
  theme: ThemeMode;
}>;

export type ProviderSlot = (
  props: Readonly<{ context: ProviderContext; children: ReactNode }>,
) => JSX.Element;

/** A QueryClient for one test: no retries, no refetch on focus, no GC mid-test. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

/**
 * Global state the providers read, set before render: the theme preference
 * ThemeProvider hydrates from, and the #v1-portal container (created by the
 * app's own getPortalContainer, themed like the root). Returns the portal.
 */
export function prepareProviders(context: ProviderContext): HTMLElement {
  useThemeStore.getState().setPreference(context.theme);
  const portal = getPortalContainer();
  portal.dataset.theme = context.theme;
  return portal;
}

/** Undoes prepareProviders; setup.ts calls it after each test. */
export function resetProviders(): void {
  document.getElementById(PORTAL_CONTAINER_ID)?.remove();
  try {
    window.localStorage.removeItem(THEME_STORAGE_KEY);
  } catch {
    // No storage, so nothing was persisted.
  }
  useThemeStore.setState(useThemeStore.getInitialState(), true);
}

const QuerySlot: ProviderSlot = ({ context, children }) => (
  <QueryClientProvider client={context.queryClient}>
    {children}
  </QueryClientProvider>
);

const RouterSlot: ProviderSlot = ({ context, children }) => (
  <MemoryRouter initialEntries={[context.route]}>
    {context.path === undefined ? (
      children
    ) : (
      <Routes>
        <Route path={context.path} element={children} />
      </Routes>
    )}
  </MemoryRouter>
);

// The app's v1 root; it hydrates the preference prepareProviders stored.
const ThemeSlot: ProviderSlot = ({ children }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

/** Outermost first. */
export const PROVIDER_SLOTS: readonly ProviderSlot[] = [
  QuerySlot,
  RouterSlot,
  ThemeSlot,
];

export function V1TestProviders({
  context,
  children,
}: Readonly<{ context: ProviderContext; children: ReactNode }>): JSX.Element {
  let tree: ReactNode = children;
  for (const Slot of [...PROVIDER_SLOTS].reverse()) {
    tree = <Slot context={context}>{tree}</Slot>;
  }
  return <>{tree}</>;
}
