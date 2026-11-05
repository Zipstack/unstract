/*
 * The v1 test harness, imported by tests as `@v1/test`. Only test files
 * (`*.test.ts(x)`, `*.spec.ts(x)`) and test/ itself may import it.
 */

export { PORTAL_CONTAINER_ID, V1_ROOT_CLASS } from "@v1/lib/portal";
export {
  type A11yOptions,
  axeViolations,
  expectNoA11yViolations,
  formatViolations,
} from "./a11y";
export {
  type IntersectionObserverControl,
  installIntersectionObserver,
  installResizeObserver,
  type MatchMediaControl,
  mockMatchMedia,
  type ResizeObserverControl,
} from "./dom";
export {
  apiPath,
  delay,
  HttpResponse,
  http,
  mockApi,
  server,
  ws,
} from "./network";
export {
  createTestQueryClient,
  type ProviderContext,
  type ProviderSlot,
} from "./providers";
export {
  type RenderV1Options,
  renderHookV1,
  renderV1,
  type V1Harness,
} from "./render";
export {
  DEFAULT_SESSION,
  DEFAULT_THEME,
  makeSession,
  type TestOrganization,
  type TestSession,
  type TestSessionOverrides,
  type TestUser,
  type ThemeMode,
} from "./session";
