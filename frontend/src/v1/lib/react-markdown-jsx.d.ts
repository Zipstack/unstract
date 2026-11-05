/*
 * react-markdown 8 (shared with v0, which keeps it on major 8) ships `.ts` type sources
 * written against React 18's global `JSX` namespace, which React 19's types
 * no longer declare, so `skipLibCheck` cannot skip them. This restores the
 * global as an alias of `React.JSX` for type checking only; no v1 code should
 * use the global form. Remove it when react-markdown is upgraded.
 */
import type { JSX as ReactJSX } from "react";

declare global {
  namespace JSX {
    type Element = ReactJSX.Element;
    type ElementClass = ReactJSX.ElementClass;
    type IntrinsicElements = ReactJSX.IntrinsicElements;
  }
}
