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
  DEFAULT_DISTRIBUTION,
  DEFAULT_SESSION,
  DEFAULT_THEME,
  type Distribution,
  type TestSession,
  type ThemeMode,
} from "./session";

export type RenderV1Options = Readonly<{
  /** The URL the router starts at. Default `/`. */
  route?: string;
  /** Mount the UI under this route pattern, so `useParams` resolves. */
  path?: string;
  /** The signed-in user; `null` renders signed out. Default DEFAULT_SESSION. */
  session?: TestSession | null;
  /** Default `oss`. */
  distribution?: Distribution;
  /** Default `light`. */
  theme?: ThemeMode;
  /** Pass one to share a cache across renders; default is a fresh client. */
  queryClient?: QueryClient;
  /** Options for the returned `user` (e.g. `{ advanceTimers }` with fake timers). */
  userEventOptions?: Parameters<typeof userEvent.setup>[0];
}>;

export type V1Harness = Readonly<{
  user: UserEvent;
  queryClient: QueryClient;
  session: TestSession | null;
  distribution: Distribution;
  theme: ThemeMode;
  /** The #v1-portal container menus, dialogs and toasts render into. */
  portal: HTMLElement;
}>;

function resolveContext(options: RenderV1Options): ProviderContext {
  return {
    queryClient: options.queryClient ?? createTestQueryClient(),
    route: options.route ?? "/",
    path: options.path,
    session: options.session === undefined ? DEFAULT_SESSION : options.session,
    distribution: options.distribution ?? DEFAULT_DISTRIBUTION,
    theme: options.theme ?? DEFAULT_THEME,
  };
}

function prepare(options: RenderV1Options) {
  const context = resolveContext(options);
  const harness: V1Harness = {
    user: userEvent.setup(options.userEventOptions),
    queryClient: context.queryClient,
    session: context.session,
    distribution: context.distribution,
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
