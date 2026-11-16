/*
 * Styling rule S1 lets a `style` attribute set CSS custom properties only
 * (`style={{ "--page-aspect": width / height }}`), the channel for runtime
 * geometry that `ui:` classes read. React's CSSProperties has no index
 * signature for `--*` keys, so without this augmentation that object literal
 * fails TS2353 under strict mode.
 */
import "react";

declare module "react" {
  interface CSSProperties {
    [property: `--${string}`]: string | number | undefined;
  }
}
