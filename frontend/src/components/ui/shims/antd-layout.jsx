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

/** antd `size` token → px gap. antd accepts a number or a preset. */
const SIZE_PX = { small: 8, middle: 16, large: 24 };

function resolveGap(size) {
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

const ALIGN = {
  start: "flex-start",
  end: "flex-end",
  center: "center",
  baseline: "baseline",
};

/**
 * antd `<Space>`. Keeps the `.ant-space` / `.ant-space-item` structure so the
 * existing CSS that targets it keeps working.
 */
const Space = React.forwardRef(function Space(
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
  const items = React.Children.toArray(children).filter(
    (c) => c !== null && c !== undefined && c !== false && c !== "",
  );

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
const Row = React.forwardRef(function Row(
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
        justifyContent: justify && (ALIGN[justify] ?? justify),
        alignItems: align && (ALIGN[align] ?? align),
        ...style,
      }}
      data-gutter={hGutter || undefined}
      {...props}
    >
      {React.Children.map(children, (child) =>
        React.isValidElement(child) && hGutter
          ? React.cloneElement(child, { __gutter: hGutter })
          : child,
      )}
    </div>
  );
});

/** antd `<Col span={1..24}>`, sharing antd's 24-column basis. */
const Col = React.forwardRef(function Col(
  { span, offset, flex, __gutter, className, style, children, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn("ant-col", className)}
      style={{
        width: span != null ? `${(span / 24) * 100}%` : undefined,
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
const Flex = React.forwardRef(function Flex(
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
        justifyContent: justify && (ALIGN[justify] ?? justify),
        alignItems: align && (ALIGN[align] ?? align),
        gap: typeof gap === "number" ? `${gap}px` : (SIZE_PX[gap] ?? gap),
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
});

export { Col, Flex, Row, Space };
