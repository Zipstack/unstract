import * as React from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * Typography primitives (P1-03).
 *
 * These deliberately mirror antd's `Typography` API — `type`, `strong`,
 * `italic`, `ellipsis`, `level` — so the ~295 call-sites become an import
 * swap rather than a hand-rewrite of every element. Per D9/§5.0 this lives in
 * OSS so cloud plugins import it too.
 *
 * Why a shim instead of plain tags + Tailwind classes: antd's `ellipsis` is
 * not styling. `ellipsis={{ tooltip: true }}` truncates AND shows the full
 * text on hover, and `ellipsis={{ rows: 2 }}` clamps to N lines. Swapping in
 * a bare `truncate` class would silently drop the tooltip — a behaviour
 * regression, which C4 forbids. `Ellipsis` below implements both.
 */

/**
 * The antd Typography surface these shims accept.
 *
 * Enumerating it is the point of the TypeScript conversion. Every bug this
 * layer has produced was a silent prop-drop: a call-site passes a prop, the
 * shim never destructures it, and `...props` swallows it with no error at all
 * (`showCount`, `onValuesChange`, `setFields`, `validateStatus` each shipped
 * that way). With an explicit interface the next one is a compile error at the
 * call-site instead of a defect in the UI.
 */
type TypographyType = "secondary" | "success" | "warning" | "danger";

/** antd's `ellipsis`: `true`, or a config object. */
type EllipsisConfig = {
  /** Lines to clamp to. Only 1–6 have a static Tailwind class; see CLAMP_CLASS. */
  rows?: number;
  /** `true` shows the element's own children on hover; a node shows that node. */
  tooltip?: boolean | React.ReactNode;
};
type EllipsisProp = boolean | EllipsisConfig;

interface TypographyCommonProps {
  type?: TypographyType;
  strong?: boolean;
  italic?: boolean;
  underline?: boolean;
  /** antd spells this `delete`; destructured as `del` since it is a keyword. */
  delete?: boolean;
  code?: boolean;
  ellipsis?: EllipsisProp;
}

/** antd `type` → Midnight Bloom token classes. */
const TYPE_CLASS: Record<TypographyType, string> = {
  secondary: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
};

/**
 * Truncation wrapper reproducing antd's `ellipsis` behaviour.
 *
 * - `true`                      → single-line truncate
 * - `{ rows: n }`               → clamp to n lines
 * - `{ tooltip: true }`         → truncate + show own text content on hover
 * - `{ tooltip: <node|string> }`→ truncate + show that content on hover
 *
 * The tooltip is always rendered when requested, rather than only when the
 * text actually overflows. antd measures the DOM to decide; matching that
 * exactly would need a resize observer per element. Showing it unconditionally
 * keeps the information reachable, which is the point of the prop.
 */
// Written out rather than interpolated (`line-clamp-${n}`): Tailwind scans
// source statically and never sees a class name built at runtime.
const CLAMP_CLASS: Record<number, string> = {
  1: "truncate whitespace-nowrap",
  2: "line-clamp-2",
  3: "line-clamp-3",
  4: "line-clamp-4",
  5: "line-clamp-5",
  6: "line-clamp-6",
};

interface EllipsisProps extends React.HTMLAttributes<HTMLElement> {
  ellipsis?: EllipsisProp;
  /** The element or component to render as, supplied by the caller. */
  Comp: React.ElementType;
}

const Ellipsis = React.forwardRef<HTMLElement, EllipsisProps>(function Ellipsis(
  { ellipsis, children, className, Comp, ...props },
  ref,
) {
  const cfg: EllipsisConfig =
    ellipsis === true || ellipsis === false || ellipsis == null ? {} : ellipsis;
  const rows = cfg.rows ?? 1;
  const clampClass = CLAMP_CLASS[rows] ?? CLAMP_CLASS[1];

  const el = (
    <Comp ref={ref} className={cn(clampClass, className)} {...props}>
      {children}
    </Comp>
  );

  if (!cfg.tooltip) {
    return el;
  }

  const tip = cfg.tooltip === true ? children : cfg.tooltip;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{el}</TooltipTrigger>
        <TooltipContent className="max-w-md break-words">{tip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
});

/** Shared prop → class handling for Text / Paragraph / Link. */
function useTypographyClass({
  type,
  strong,
  italic,
  underline,
  del,
  code,
}: Omit<TypographyCommonProps, "delete" | "ellipsis"> & { del?: boolean }) {
  return cn(
    // ~8 CSS rules target .ant-typography (margins, line-height).
    "ant-typography",
    strong && "ant-typography-strong",
    type && TYPE_CLASS[type],
    strong && "font-semibold",
    italic && "italic",
    underline && "underline",
    del && "line-through",
    /*
     * antd's inline code has a BORDER as well as a fill — that outline is what
     * makes it read as code. `bg-muted` alone is #f5f5f5, five values off the
     * #fafafa surface it sits on, so the snippets in Custom Data were
     * indistinguishable from body text.
     */
    code &&
      "rounded border border-separator bg-muted px-1 py-0.5 font-mono text-[0.85em] text-foreground",
  );
}

interface TextProps
  extends TypographyCommonProps,
    Omit<React.HTMLAttributes<HTMLElement>, "color"> {
  /** Renders a <mark> instead of a <span>. */
  mark?: boolean;
}

/** antd `<Typography.Text>`. Renders a <span>. */
const Text = React.forwardRef<HTMLElement, TextProps>(function Text(
  {
    className,
    type,
    strong,
    italic,
    underline,
    delete: del,
    code,
    mark,
    ellipsis,
    children,
    ...props
  },
  ref,
) {
  const base = useTypographyClass({
    type,
    strong,
    italic,
    underline,
    del,
    code,
  });
  const Comp = mark ? "mark" : "span";

  if (ellipsis) {
    return (
      <Ellipsis
        Comp={Comp}
        ellipsis={ellipsis}
        className={cn("inline-block max-w-full align-bottom", base, className)}
        ref={ref}
        {...props}
      >
        {children}
      </Ellipsis>
    );
  }

  return (
    <Comp ref={ref} className={cn(base, className)} {...props}>
      {children}
    </Comp>
  );
});

interface TitleProps
  extends TypographyCommonProps,
    Omit<React.HTMLAttributes<HTMLHeadingElement>, "color"> {
  level?: 1 | 2 | 3 | 4 | 5 | 6;
}

/** antd `<Typography.Title level={1..5}>`. Renders the matching heading. */
const Title = React.forwardRef<HTMLHeadingElement, TitleProps>(function Title(
  { className, level = 1, type, ellipsis, children, ...props },
  ref,
) {
  const Comp = `h${Math.min(Math.max(level, 1), 6)}` as React.ElementType;
  const size: string | undefined = {
    1: "text-3xl font-bold tracking-tight",
    2: "text-2xl font-semibold tracking-tight",
    3: "text-xl font-semibold",
    4: "text-lg font-semibold",
    5: "text-base font-semibold",
    6: "text-sm font-semibold",
  }[level];

  if (ellipsis) {
    return (
      <Ellipsis
        Comp={Comp}
        ellipsis={ellipsis}
        className={cn(size, type && TYPE_CLASS[type], className)}
        ref={ref}
        {...props}
      >
        {children}
      </Ellipsis>
    );
  }

  return (
    <Comp
      ref={ref}
      className={cn(size, type && TYPE_CLASS[type], className)}
      {...props}
    >
      {children}
    </Comp>
  );
});

interface ParagraphProps
  extends TypographyCommonProps,
    Omit<React.HTMLAttributes<HTMLParagraphElement>, "color"> {}

/** antd `<Typography.Paragraph>`. Renders a <p>. */
const Paragraph = React.forwardRef<HTMLParagraphElement, ParagraphProps>(
  function Paragraph(
    { className, type, strong, italic, ellipsis, children, ...props },
    ref,
  ) {
    const base = useTypographyClass({ type, strong, italic });

    if (ellipsis) {
      return (
        <Ellipsis
          Comp="p"
          ellipsis={ellipsis}
          className={cn(base, className)}
          ref={ref}
          {...props}
        >
          {children}
        </Ellipsis>
      );
    }

    return (
      <p ref={ref} className={cn(base, className)} {...props}>
        {children}
      </p>
    );
  },
);

interface LinkProps
  extends TypographyCommonProps,
    Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "color" | "type"> {}

/**
 * antd `<Typography.Link>`. Renders an <a>.
 * NOTE: unrelated to react-router's `Link` — the 3 call-sites that use
 * react-router keep importing it from there.
 */
const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  { className, type, strong, italic, children, ...props },
  ref,
) {
  const base = useTypographyClass({ type, strong, italic });
  return (
    <a
      ref={ref}
      className={cn(
        "cursor-pointer text-primary underline-offset-4 hover:underline",
        base,
        className,
      )}
      {...props}
    >
      {children}
    </a>
  );
});

/**
 * Namespace object so `<Typography.Text>` call-sites work with only an import
 * change — matching how antd exposes these.
 */
const Typography = Object.assign(
  React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
    function Typography({ className, children, ...props }, ref) {
      return (
        <div ref={ref} className={cn(className)} {...props}>
          {children}
        </div>
      );
    },
  ),
  { Text, Title, Paragraph, Link },
);

export { Link, Paragraph, Text, Title, Typography };
