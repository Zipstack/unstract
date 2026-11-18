import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "@v1/app/query";
import { ThemeProvider } from "@v1/app/theme/ThemeProvider";
import { getPortalContainer, PORTAL_CONTAINER_ID } from "@v1/lib/portal";
import { SessionProvider } from "@v1/lib/session";
import { THEME_STORAGE_KEY } from "@v1/lib/theme";
import { setOrganizationId } from "@v1/services/context";
import { useThemeStore } from "@v1/stores/theme";
import type { JSX, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { type TestSession, type ThemeMode, toV1Session } from "./session";

/*
 * The v1 provider chain for tests: the ONLY file to edit when a real provider
 * lands. A slot is the app's own provider once its task has merged, and a
 * stand-in until then:
 *
 *   query   real      app/query (P0-T05, UN-4313), with test defaults
 *   router  stand-in  P0-T03 router + registry (UN-4271) → the app's router, in memory
 *   theme   real      app/theme/ThemeProvider (P0-T04, #2399)
 *   session real      lib/session's SessionProvider (P0-T06, UN-4314) and the org services/ use
 *
 * Swap a slot by changing its entry in PROVIDER_SLOTS (and, if it holds
 * global state, prepareProviders / resetProviders); renderV1 and every test
 * stay as they are. See README.md in this folder.
 *
 * Every field here is read by a slot. A new one (a distribution) arrives
 * together with the slot that reads it, never ahead of it.
 */

/** Everything a slot may need, resolved from renderV1's options. */
export type ProviderContext = Readonly<{
  queryClient: QueryClient;
  /** The URL the router starts at. */
  route: string;
  /** A route pattern to mount the UI under, so `useParams` resolves. */
  path: string | undefined;
  theme: ThemeMode;
  /** The signed-in session; null renders as a guest. */
  session: TestSession | null;
}>;

export type ProviderSlot = (
  props: Readonly<{ context: ProviderContext; children: ReactNode }>,
) => JSX.Element;

/** The app's QueryClient for one test: no retries, no refetch on focus, no GC mid-test. */
export function createTestQueryClient(): QueryClient {
  return createQueryClient({
    queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false },
    mutations: { retry: false },
  });
}

/**
 * Global state the providers read, set before render: the theme preference
 * ThemeProvider hydrates from, and the #v1-portal container (created by the
 * app's own getPortalContainer, themed like the root). Returns the portal.
 */
export function prepareProviders(context: ProviderContext): HTMLElement {
  useThemeStore.getState().setPreference(context.theme);
  setOrganizationId(context.session?.organization.id ?? null);
  const portal = getPortalContainer();
  portal.dataset.theme = context.theme;
  return portal;
}

/** Undoes prepareProviders; setup.ts calls it after each test. */
export function resetProviders(): void {
  document.getElementById(PORTAL_CONTAINER_ID)?.remove();
  setOrganizationId(null);
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

// What RouteGate provides once the session allows the page.
const SessionSlot: ProviderSlot = ({ context, children }) => (
  <SessionProvider
    session={context.session ? toV1Session(context.session) : null}
  >
    {children}
  </SessionProvider>
);

/** Outermost first. */
export const PROVIDER_SLOTS: readonly ProviderSlot[] = [
  QuerySlot,
  RouterSlot,
  ThemeSlot,
  SessionSlot,
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
