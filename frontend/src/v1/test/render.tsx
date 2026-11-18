import type { QueryClient } from "@tanstack/react-query";
import {
  type RenderHookResult,
  type RenderResult,
  render,
  renderHook,
} from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import type { ReactNode } from "react";
import {
  createTestQueryClient,
  type ProviderContext,
  prepareProviders,
  V1TestProviders,
} from "./providers";
import {
  DEFAULT_SESSION,
  DEFAULT_THEME,
  type TestSession,
  type ThemeMode,
} from "./session";

export type RenderV1Options = Readonly<{
  /** The URL the router starts at. Default `/`. */
  route?: string;
  /** Mount the UI under this route pattern, so `useParams` resolves. */
  path?: string;
  /** Default `light`. */
  theme?: ThemeMode;
  /** The signed-in session `useSession()` gives, and the org services call; null for a guest. Default DEFAULT_SESSION. */
  session?: TestSession | null;
  /** Pass one to share a cache across renders; default is a fresh client. */
  queryClient?: QueryClient;
  /** Options for the returned `user` (e.g. `{ advanceTimers }` with fake timers). */
  userEventOptions?: Parameters<typeof userEvent.setup>[0];
}>;

export type V1Harness = Readonly<{
  user: UserEvent;
  queryClient: QueryClient;
  theme: ThemeMode;
  /** The #v1-portal container menus, dialogs and toasts render into. */
  portal: HTMLElement;
}>;

/*
 * No provider reads a distribution yet, so renderV1 takes none: an option no
 * provider consumes would let a test of a cloud-only branch pass without
 * reaching it. It comes back with the slot that reads it (see README.md).
 * Until then a caller that passes one anyway (a cast, plain JS) fails loudly.
 */
const NOT_YET_CONSUMED = ["distribution"] as const;

function rejectUnconsumedOptions(options: object): void {
  const passed = NOT_YET_CONSUMED.filter((key) => key in options);
  if (passed.length > 0) {
    throw new Error(
      `renderV1: ${passed.join(" and ")} is not supported yet; no v1 provider reads it, so the test would not exercise what it sets. See src/v1/test/README.md.`,
    );
  }
}

function resolveContext(options: RenderV1Options): ProviderContext {
  rejectUnconsumedOptions(options);
  return {
    queryClient: options.queryClient ?? createTestQueryClient(),
    route: options.route ?? "/",
    path: options.path,
    theme: options.theme ?? DEFAULT_THEME,
    session: options.session === undefined ? DEFAULT_SESSION : options.session,
  };
}

function prepare(options: RenderV1Options) {
  const context = resolveContext(options);
  const harness: V1Harness = {
    user: userEvent.setup(options.userEventOptions),
    queryClient: context.queryClient,
    theme: context.theme,
    portal: prepareProviders(context),
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <V1TestProviders context={context}>{children}</V1TestProviders>
  );
  return { harness, wrapper };
}

/** Renders `ui` inside the v1 providers. */
export function renderV1(
  ui: ReactNode,
  options: RenderV1Options = {},
): RenderResult & V1Harness {
  const { harness, wrapper } = prepare(options);
  const result: RenderResult = render(ui, { wrapper });
  return { ...result, ...harness };
}

/** Renders a hook inside the v1 providers. */
export function renderHookV1<Result, Props = undefined>(
  hook: (props: Props) => Result,
  options: RenderV1Options & Readonly<{ initialProps?: Props }> = {},
): RenderHookResult<Result, Props> & V1Harness {
  const { harness, wrapper } = prepare(options);
  const result: RenderHookResult<Result, Props> = renderHook<Result, Props>(
    hook,
    { wrapper, initialProps: options.initialProps },
  );
  return { ...result, ...harness };
}
