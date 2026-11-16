/*
 * The component for each declared page, loaded on first render. Add a
 * page's line here when it is declared in PAGES; validate.test.ts fails if a
 * declared page has none.
 */

import type { PageKey } from "@v1/app/registry/types";
import { type JSX, type LazyExoticComponent, lazy } from "react";

type PageComponent = LazyExoticComponent<() => JSX.Element>;

export const PAGE_COMPONENTS: Readonly<
  Partial<Record<PageKey, PageComponent>>
> = {
  "DEMO-PAGE": lazy(() =>
    import("@v1/pages/demo").then((m) => ({ default: m.DemoPage })),
  ),
  "DEMO-REVIEW": lazy(() =>
    import("@v1/pages/demo").then((m) => ({ default: m.DemoReviewPage })),
  ),
};
