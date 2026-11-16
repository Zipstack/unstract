/*
 * Types for react-markdown 8, which src/v1/tsconfig.json maps "react-markdown"
 * to (type checking only: Vite and Vitest still load the real package).
 *
 * react-markdown 8, shared with v0 and kept on major 8 there, ships `.ts` type
 * sources written against React 18's global `JSX` namespace. React 19's types
 * no longer declare it, and `skipLibCheck` cannot skip `.ts` files, so the
 * real types fail `typecheck:v1`. This stub declares only what v1 uses, so the
 * global `JSX` stays undeclared for v1 code. Delete it, and the `paths` entry,
 * when react-markdown is upgraded. The root tsconfig has no such mapping: once
 * v0 imports something from `@v1` that reaches Markdown.tsx (the version
 * switch, UN-4271), root `tsc` meets the real types and needs the same fix.
 */
import type { JSX } from "react";

/** Keeps http(s), mailto, tel and relative URLs; turns any other into `javascript:void(0)`. */
export function uriTransformer(uri: string): string;

/** The subset of react-markdown 8's `Options` that v1 passes (same name as the package's). */
export type Options = Readonly<{
  children: string;
  remarkPlugins?: readonly unknown[];
  skipHtml?: boolean;
  transformLinkUri?: (
    href: string,
    children: unknown[],
    title: string | null,
  ) => string;
  transformImageUri?: (
    src: string,
    alt: string,
    title: string | null,
  ) => string;
  /** Element name to component; each receives the element's props plus react-markdown's own. */
  components?: Readonly<Record<string, unknown>>;
}>;

declare function ReactMarkdown(options: Options): JSX.Element;
export default ReactMarkdown;
