import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { JSX, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Distribution, TestSession, ThemeMode } from "./session";

/*
 * The v1 provider chain for tests: the ONLY file to edit when a real provider
 * lands. Each slot is a stand-in until its task merges:
 *
 *   query   P0-T05 data layer (UN-4313)    → the app's QueryClient provider
 *   router  P0-T03 router + registry (UN-4271) → the app's router, in memory
 *   theme   P0-T04 tokens + theme (#2399)  → app/theme/ThemeProvider
 *
 * Swap a slot by changing its entry in PROVIDER_SLOTS; renderV1 and every
 * test stay as they are. See README.md in this folder.
 */

/** Everything a slot may need, resolved from renderV1's options. */
export type ProviderContext = Readonly<{
  queryClient: QueryClient;
  /** The URL the router starts at. */
  route: string;
  /** A route pattern to mount the UI under, so `useParams` resolves. */
  path: string | undefined;
  session: TestSession | null;
  distribution: Distribution;
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

/** The single element under <body> that v1 dialogs, menus and toasts render into (#2399). */
export const PORTAL_CONTAINER_ID = "v1-portal";

/** The class that scopes v1 styles (#2399). */
export const V1_ROOT_CLASS = "v1";

/** Creates (or re-themes) the #v1-portal container, as #2399's getPortalContainer does. */
export function ensurePortalContainer(theme: ThemeMode): HTMLElement {
  let container = document.getElementById(PORTAL_CONTAINER_ID);
  if (!container) {
    container = document.createElement("div");
    container.id = PORTAL_CONTAINER_ID;
    container.className = V1_ROOT_CLASS;
    document.body.appendChild(container);
  }
  container.dataset.theme = theme;
  return container;
}

/** Removes the portal container; setup.ts calls it after each test. */
export function removePortalContainer(): void {
  document.getElementById(PORTAL_CONTAINER_ID)?.remove();
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

// Matches #2399's ThemeProvider output: the v1 root, versioned and themed.
const ThemeSlot: ProviderSlot = ({ context, children }) => (
  <div
    className={V1_ROOT_CLASS}
    data-ui-version="v1"
    data-theme={context.theme}
  >
    {children}
  </div>
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
