import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * antd-compatible layout primitives: `Space`, `Row`, `Col`, `Flex` (P1-05).
 *
 * The plan called these a direct swap to flex/grid utilities. That is unsafe
 * here for one specific reason: **antd's `Space` wraps every child in its own
 * `.ant-space-item` div**, and `Row`/`Col` emit `.ant-row`/`.ant-col`. This
 * repo has 20 hand-written CSS rules that select those internals
 * (`.ant-space .ant-space-item .ant-card`, `.file-history-modal .ant-space`,
 * `.ant-row`/`.ant-col` …). Collapsing the wrappers into `gap-*` on the parent
 * deletes the elements those selectors match, so the styling silently stops
 * applying — a regression, not a restyle (C4).
 *
 * 22 `Space` call-sites also render children from `.map()` or conditionals,
 * where per-child wrappers change what `> *` matches.
 *
 * These components therefore keep antd's DOM shape (including the class names
 * the existing CSS targets) while dropping the antd dependency. The legacy
 * `ant-*` class names are emitted deliberately, and go away in P4 when the
 * dependent CSS is cleaned up.
 */

/**
 * The antd layout surface these shims accept.
 *
 * Enumerated by hand rather than inferred: the failure mode this whole layer
 * has is the silent prop-drop, where a call-site passes something the shim
 * never destructures and `...props` swallows it without a warning. Naming
 * each prop turns the next one into a compile error at the call-site.
 */
type SizeToken = "small" | "middle" | "large";
type AlignToken = "start" | "end" | "center" | "baseline";

/** antd accepts a token, a raw px number, or a [horizontal, vertical] pair. */
type SpaceSize = SizeToken | number | Array<SizeToken | number>;

interface SpaceProps extends React.HTMLAttributes<HTMLDivElement> {
  direction?: "horizontal" | "vertical";
  size?: SpaceSize;
  align?: AlignToken;
  wrap?: boolean;
  /** Rendered between items, as antd does. */
  split?: React.ReactNode;
}

interface RowProps extends React.HTMLAttributes<HTMLDivElement> {
  /** px, or [horizontal, vertical] px. */
  gutter?: number | [number, number];
  justify?: AlignToken | React.CSSProperties["justifyContent"];
  align?: AlignToken | React.CSSProperties["alignItems"];
  wrap?: boolean;
}

/** antd's responsive Col props, smallest breakpoint first. */
type ColBreakpoint = "xs" | "sm" | "md" | "lg" | "xl" | "xxl";

interface ColProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Width in 24ths, antd's grid basis. */
  span?: number;
  offset?: number;
  flex?: React.CSSProperties["flex"];
  /*
   * antd's per-breakpoint widths, also in 24ths. These were not destructured,
   * so `<Col xs={24}>` fell into `...props`, reached the DOM as an unknown
   * attribute, and the column got NO width at all — the Dashboard's "Usage by
   * Deployment" card shrank to fit its empty state instead of spanning the row.
   */
  xs?: number;
  sm?: number;
  md?: number;
  lg?: number;
  xl?: number;
  xxl?: number;
  /**
   * Internal: Row clones its children to pass its gutter down for padding.
   * Not part of antd's API and not meant for call-sites.
   */
  __gutter?: number;
}

interface FlexProps extends React.HTMLAttributes<HTMLDivElement> {
  vertical?: boolean;
  justify?: AlignToken | React.CSSProperties["justifyContent"];
  align?: AlignToken | React.CSSProperties["alignItems"];
  gap?: SizeToken | number;
  wrap?: boolean;
}

/** antd `size` token → px gap. antd accepts a number or a preset. */
const SIZE_PX: Record<SizeToken, number> = {
  small: 8,
  middle: 16,
  large: 24,
};

function resolveGap(size?: SpaceSize): number | number[] {
  if (size == null) {
    return SIZE_PX.small;
  }
  if (typeof size === "number") {
    return size;
  }
  if (Array.isArray(size)) {
    return size.map((s) => (typeof s === "number" ? s : (SIZE_PX[s] ?? 8)));
  }
  return SIZE_PX[size] ?? SIZE_PX.small;
}

/**
 * antd tokens differ from the CSS keywords: antd says `start`, flexbox wants
 * `flex-start`. Call-sites pass either, so translate what we recognise and
 * hand anything else to CSS untouched.
 */
function toCssAlign<T extends string | undefined>(
  value: T,
): string | undefined {
  if (value == null) {
    return undefined;
  }
  return ALIGN[value as AlignToken] ?? value;
}

const ALIGN: Record<AlignToken, string> = {
  start: "flex-start",
  end: "flex-end",
  center: "center",
  baseline: "baseline",
};

/**
 * antd counts `Space`'s children with rc-util's `toArray`, which **descends
 * into fragments**; React's own `Children.toArray` does not — it counts
 * `<>…</>` as a single child.
 *
 * That difference is not cosmetic. A call-site that renders its items behind
 * `{cond && <>…</>}` (the LLMWhisperer playground header does) collapsed into
 * one `.ant-space-item`, so the gap between them disappeared and any
 * block-level child — a vertical `Divider` — broke onto its own line, which
 * stacked the header vertically.
 */
function flattenFragments(children: React.ReactNode): React.ReactNode[] {
  return React.Children.toArray(children).flatMap((child) =>
    React.isValidElement(child) && child.type === React.Fragment
      ? flattenFragments(
          (child.props as { children?: React.ReactNode }).children,
        )
      : [child],
  );
}

/**
 * antd `<Space>`. Keeps the `.ant-space` / `.ant-space-item` structure so the
 * existing CSS that targets it keeps working.
 */
const Space = React.forwardRef<HTMLDivElement, SpaceProps>(function Space(
  {
    direction = "horizontal",
    size,
    align,
    wrap,
    split,
    className,
    style,
    children,
    ...props
  },
  ref,
) {
  const gap = resolveGap(size);
  // toArray already discards null, undefined and booleans, so the empty
  // string is the only falsy child left worth dropping.
  const items = flattenFragments(children).filter((c) => c !== "");

  return (
    <div
      ref={ref}
      className={cn(
        "ant-space inline-flex",
        direction === "vertical"
          ? "ant-space-vertical"
          : "ant-space-horizontal",
        direction === "vertical" ? "flex-col" : "flex-row",
        wrap && "flex-wrap",
        className,
      )}
      style={{
        gap: Array.isArray(gap)
          ? `${gap[1] ?? gap[0]}px ${gap[0]}px`
          : `${gap}px`,
        alignItems:
          align != null
            ? ALIGN[align]
            : direction === "vertical"
              ? undefined
              : "center",
        ...style,
      }}
      {...props}
    >
      {items.map((child, i) => (
        // The wrapper div is the whole point: existing CSS selects it.
        // eslint-disable-next-line react/no-array-index-key
        <div key={i} className="ant-space-item">
          {child}
          {split && i < items.length - 1 ? split : null}
        </div>
      ))}
    </div>
  );
});

/** antd `<Row>`. antd's 24-column grid, with the `.ant-row` hook preserved. */
const Row = React.forwardRef<HTMLDivElement, RowProps>(function Row(
  { gutter, justify, align, wrap = true, className, style, children, ...props },
  ref,
) {
  const [hGutter, vGutter] = Array.isArray(gutter) ? gutter : [gutter ?? 0, 0];

  return (
    <div
      ref={ref}
      className={cn("ant-row flex", wrap && "flex-wrap", className)}
      style={{
        marginLeft: hGutter ? -hGutter / 2 : undefined,
        marginRight: hGutter ? -hGutter / 2 : undefined,
        rowGap: vGutter || undefined,
        justifyContent: toCssAlign(justify),
        alignItems: toCssAlign(align),
        ...style,
      }}
      data-gutter={hGutter || undefined}
      {...props}
    >
      {React.Children.map(children, (child) =>
        React.isValidElement<ColProps>(child) && hGutter
          ? React.cloneElement(child, { __gutter: hGutter })
          : child,
      )}
    </div>
  );
});

/** antd `<Col span={1..24}>`, sharing antd's 24-column basis. */
const COL_BREAKPOINTS: ColBreakpoint[] = ["xs", "sm", "md", "lg", "xl", "xxl"];

const Col = React.forwardRef<HTMLDivElement, ColProps>(function Col(
  {
    span,
    offset,
    flex,
    __gutter,
    xs,
    sm,
    md,
    lg,
    xl,
    xxl,
    className,
    style,
    children,
    ...props
  },
  ref,
) {
  /*
   * antd picks the value for the LARGEST breakpoint the viewport satisfies,
   * falling back to `span`. Reproducing that faithfully would need a media
   * query per column; in practice every call-site here either passes `span`
   * alone or repeats the same value across breakpoints (`xs={24}`), so the
   * largest specified value is the effective one on a desktop viewport.
   */
  const responsive = { xs, sm, md, lg, xl, xxl };
  const widest = COL_BREAKPOINTS.reduce<number | undefined>(
    (acc, bp) => (responsive[bp] != null ? responsive[bp] : acc),
    undefined,
  );
  const effectiveSpan = widest ?? span;

  return (
    <div
      ref={ref}
      className={cn("ant-col", className)}
      style={{
        width:
          effectiveSpan != null ? `${(effectiveSpan / 24) * 100}%` : undefined,
        marginLeft: offset != null ? `${(offset / 24) * 100}%` : undefined,
        flex: flex ?? undefined,
        paddingLeft: __gutter ? __gutter / 2 : undefined,
        paddingRight: __gutter ? __gutter / 2 : undefined,
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
});

/**
 * antd `<Flex>`. This one genuinely is a thin styling wrapper — no per-child
 * divs, no CSS in this repo targeting `.ant-flex` — but it lives here so the
 * four layout components are imported from one place.
 */
const Flex = React.forwardRef<HTMLDivElement, FlexProps>(function Flex(
  { vertical, justify, align, gap, wrap, className, style, children, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        "flex",
        vertical && "flex-col",
        wrap && "flex-wrap",
        className,
      )}
      style={{
        justifyContent: toCssAlign(justify),
        alignItems: toCssAlign(align),
        gap:
          typeof gap === "number"
            ? `${gap}px`
            : gap != null
              ? `${SIZE_PX[gap] ?? gap}px`
              : undefined,
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
});

export { Col, Flex, Row, Space };
