import "react";

// v1 sets runtime geometry through CSS custom properties on `style` (S1 allows
// only `--*` keys there), so the style type has to accept them.
declare module "react" {
  interface CSSProperties {
    [property: `--${string}`]: string | number | undefined;
  }
}
