import {
  CircleAlert,
  CircleCheck,
  Inbox,
  Info,
  TriangleAlert,
  X,
} from "lucide-react";
import * as React from "react";

import {
  AlertDescription,
  AlertTitle,
  Alert as ShadcnAlert,
} from "@/components/ui/alert";
import {
  AvatarFallback,
  AvatarImage,
  Avatar as ShadcnAvatar,
} from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Progress as ShadcnProgress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/**
 * antd-compatible leaf components (P1-06): Tag, Spin, Alert, Image, Divider,
 * Empty, Avatar, Progress.
 *
 * These are the "direct swap" tier per docs/shim-convention.md — the antd
 * originals carry no behaviour the shadcn primitives lack. They are gathered
 * here anyway so the call-sites convert by import rather than by rewriting
 * ~60 JSX blocks by hand, which keeps the diff mechanical and reviewable (C4).
 *
 * Notable: `Spin` has ZERO `spinning={...}` usages in this codebase, so no
 * overlay-mode wrapper is needed — every site is a bare indicator.
 */

/** antd Tag colour token → Badge variant / class. */
/**
 * The antd surface these leaf shims accept.
 *
 * Enumerated by hand rather than inferred, for the reason this whole layer
 * exists: an unrecognised prop falls into `...props` and disappears without a
 * warning. Naming each one makes the next omission a compile error at the
 * call-site.
 */
type TagColor =
  | "success"
  | "processing"
  | "error"
  | "warning"
  | "default"
  | "blue"
  | "green"
  | "red"
  | "orange"
  | "purple"
  | "cyan"
  | "magenta"
  | "gold"
  | "lime"
  | "geekblue"
  | "volcano";

type AlertType = "success" | "info" | "warning" | "error";

interface TagProps extends React.HTMLAttributes<HTMLDivElement> {
  /** A known token maps to a variant; anything else is used as a raw colour. */
  color?: TagColor | string;
  icon?: React.ReactNode;
  closable?: boolean;
  onClose?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  bordered?: boolean;
}

interface SpinProps extends React.HTMLAttributes<HTMLElement> {
  size?: "small" | "default" | "large";
  /** Caption rendered beside the spinner. */
  tip?: React.ReactNode;
  /**
   * Wrapper form only. antd defaults it to `true`, so `<Spin>{children}</Spin>`
   * with no `spinning` shows the overlay.
   */
  spinning?: boolean;
}

interface AlertProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "children"> {
  message?: React.ReactNode;
  description?: React.ReactNode;
  type?: AlertType;
  showIcon?: boolean;
  closable?: boolean;
  onClose?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  /** Full-width banner styling, as antd does. */
  banner?: boolean;
  action?: React.ReactNode;
}

interface ImageProps
  extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, "width" | "height"> {
  width?: number | string;
  height?: number | string;
  /** antd opens a lightbox; accepted so call-sites keep compiling. */
  preview?: boolean;
  /** Shown when the image fails to load. */
  fallback?: string;
}

interface DividerProps extends React.HTMLAttributes<HTMLDivElement> {
  type?: "horizontal" | "vertical";
}

interface EmptyProps extends React.HTMLAttributes<HTMLDivElement> {
  description?: React.ReactNode;
  image?: React.ReactNode;
}

interface AvatarProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> {
  /** A token, or an explicit pixel size. */
  size?: "small" | "default" | "large" | number;
  shape?: "circle" | "square";
  src?: string;
  icon?: React.ReactNode;
  alt?: string;
  children?: React.ReactNode;
}

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  percent?: number;
  status?: "success" | "exception" | "normal" | "active";
  showInfo?: boolean;
}

/*
 * antd's preset tag colours, read off the reference's own stylesheet.
 *
 * These were mapped onto shadcn Badge VARIANTS, which are solid fills — so
 * `<Tag color="orange">` rendered as white-on-brown where antd draws a pale
 * amber chip with saturated text. antd's presets are always tinted: a very
 * light background, a strong foreground, and a mid-tone border. Reproduce the
 * palette rather than approximating it with three variants.
 */
const TAG_PRESET: Record<string, { fg: string; bg: string; border: string }> = {
  red: { fg: "#cf1322", bg: "#fff1f0", border: "#ffa39e" },
  volcano: { fg: "#d4380d", bg: "#fff2e8", border: "#ffbb96" },
  orange: { fg: "#d46b08", bg: "#fff7e6", border: "#ffd591" },
  gold: { fg: "#d48806", bg: "#fffbe6", border: "#ffe58f" },
  lime: { fg: "#7cb305", bg: "#fcffe6", border: "#eaff8f" },
  green: { fg: "#389e0d", bg: "#f6ffed", border: "#b7eb8f" },
  cyan: { fg: "#08979c", bg: "#e6fffb", border: "#87e8de" },
  blue: { fg: "#0958d9", bg: "#e6f4ff", border: "#91caff" },
  geekblue: { fg: "#1d39c4", bg: "#f0f5ff", border: "#adc6ff" },
  purple: { fg: "#531dab", bg: "#f9f0ff", border: "#d3adf7" },
  magenta: { fg: "#c41d7f", bg: "#fff0f6", border: "#ffadd2" },
  // antd's status aliases resolve to the same chips.
  success: { fg: "#389e0d", bg: "#f6ffed", border: "#b7eb8f" },
  error: { fg: "#cf1322", bg: "#fff1f0", border: "#ffa39e" },
  warning: { fg: "#d46b08", bg: "#fff7e6", border: "#ffd591" },
  processing: { fg: "#0958d9", bg: "#e6f4ff", border: "#91caff" },
};

/** antd `<Tag>`. Custom colours (e.g. `rgb(...)`) fall through to inline style. */
const Tag = React.forwardRef<HTMLDivElement, TagProps>(function Tag(
  {
    color,
    icon,
    closable,
    onClose,
    bordered,
    className,
    style,
    children,
    ...props
  },
  ref,
) {
  const preset = color
    ? TAG_PRESET[color as keyof typeof TAG_PRESET]
    : undefined;
  // A raw CSS colour (e.g. `rgb(...)`) antd would have applied directly as a
  // solid fill; only presets get the tinted treatment.
  const custom = color && !preset ? color : undefined;

  return (
    <Badge
      ref={ref}
      variant="secondary"
      /*
       * `[&>svg]:size-3` sizes the `icon` prop. antd's icons were a font and
       * inherited the tag's font-size; lucide ships SVGs that carry
       * width/height 24, and index.css's inline-icon rule cannot reach them
       * because Badge is `inline-flex` (that rule deliberately skips flex
       * parents). Without this a `<Tag icon={…}>` renders a 24px glyph beside
       * 12px text — e.g. the HITL reviewer chip in FetchSpecificModal.
       */
      className={cn(
        "ant-tag gap-1 border font-normal [&>svg]:size-3",
        className,
      )}
      style={
        preset
          ? {
              backgroundColor: preset.bg,
              borderColor: preset.border,
              color: preset.fg,
              ...style,
            }
          : custom
            ? {
                backgroundColor: custom,
                borderColor: custom,
                color: "#fff",
                ...style,
              }
            : style
      }
      {...props}
    >
      {icon}
      {children}
      {closable ? (
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-0.5 cursor-pointer"
        >
          <X className="size-3" />
        </button>
      ) : null}
    </Badge>
  );
});

/**
 * antd `<Spin>`, in both of its forms.
 *
 * This shim used to handle only the bare indicator and said so in a comment.
 * That was wrong: three plugins use the WRAPPER form,
 * `<Spin spinning={loading}>{content}</Spin>`, and because the old body
 * destructured `{size, tip, className, ...props}` and then supplied its own
 * JSX children, `props.children` was silently discarded — the content it
 * wrapped never rendered at all. FetchSpecificModal showed a permanently
 * spinning dialog with no document list and no empty state; `spinning` also
 * leaked onto the DOM as an unknown attribute. Hence the explicit `children`
 * binding below, which is what makes the drop impossible to reintroduce.
 *
 * Class names follow antd's real structure: `ant-spin-nested-loading` on the
 * outer box and `ant-spin-container` on the child that gets blurred. The old
 * code put `ant-spin-container` on the bare indicator, which is neither
 * antd's meaning nor something any stylesheet relied on.
 */
const Spin = React.forwardRef<HTMLElement, SpinProps>(function Spin(
  { size, tip, spinning = true, className, children, ...props },
  ref,
) {
  const mapped = size === "large" ? "lg" : size === "small" ? "sm" : "default";
  const indicator = (
    <>
      <Spinner size={mapped} />
      {tip ? (
        <span className="text-sm text-muted-foreground">{tip}</span>
      ) : null}
    </>
  );

  if (children === undefined) {
    return (
      <span
        ref={ref as React.Ref<HTMLSpanElement>}
        className={cn("inline-flex items-center gap-2", className)}
        {...props}
      >
        {indicator}
      </span>
    );
  }

  return (
    <div
      ref={ref as React.Ref<HTMLDivElement>}
      className={cn("ant-spin-nested-loading relative", className)}
      {...props}
    >
      {spinning ? (
        <span className="absolute inset-0 z-10 flex items-center justify-center gap-2">
          {indicator}
        </span>
      ) : null}
      {/*
       * antd dims and freezes the wrapped content rather than unmounting it,
       * so scroll position and focus survive a reload. `aria-busy` is what
       * tells a screen reader the region is stale, since the spinner itself
       * carries no text.
       */}
      <div
        className={cn(
          "ant-spin-container",
          spinning && "pointer-events-none select-none opacity-50",
        )}
        aria-busy={spinning}
      >
        {children}
      </div>
    </div>
  );
});

const ALERT_ICON = {
  success: CircleCheck,
  info: Info,
  warning: TriangleAlert,
  error: CircleAlert,
};

/** antd `<Alert message description type showIcon closable banner />`. */
const Alert = React.forwardRef<HTMLDivElement, AlertProps>(function Alert(
  {
    message,
    description,
    type = "info",
    showIcon,
    closable,
    onClose,
    banner,
    action,
    className,
    ...props
  },
  ref,
) {
  const [open, setOpen] = React.useState(true);
  const Icon = ALERT_ICON[type] ?? Info;

  if (!open) {
    return null;
  }

  return (
    <ShadcnAlert
      ref={ref}
      variant={type === "error" ? "destructive" : "default"}
      className={cn(
        type === "success" && "border-success/40 text-success",
        type === "warning" && "border-warning/40 text-warning",
        /*
         * antd tints info alerts BLUE (colorInfoBg #e6f4ff, colorInfo
         * #1677ff). `info` had no branch at all, so it fell through to the
         * plain default variant and the "Highlight Feature Availability"
         * notice rendered as a neutral grey box with none of the visual
         * language of an info message.
         */
        type === "info" && "border-info/40 bg-info-bg [&>svg]:text-info",
        banner && "rounded-none border-x-0",
        className,
      )}
      {...props}
    >
      {showIcon ? <Icon className="size-4" /> : null}
      {message ? <AlertTitle>{message}</AlertTitle> : null}
      {description ? <AlertDescription>{description}</AlertDescription> : null}
      {action}
      {closable ? (
        <button
          type="button"
          aria-label="Close"
          className="absolute right-3 top-3 cursor-pointer"
          onClick={(e) => {
            setOpen(false);
            onClose?.(e);
          }}
        >
          <X className="size-4" />
        </button>
      ) : null}
    </ShadcnAlert>
  );
});

/** antd `<Image>`. `preview` is not reimplemented — no call-site enables it. */
const Image = React.forwardRef<HTMLImageElement, ImageProps>(function Image(
  {
    src,
    alt = "",
    width,
    height,
    preview,
    fallback,
    className,
    style,
    ...props
  },
  ref,
) {
  return (
    <img
      ref={ref}
      src={src}
      alt={alt}
      className={cn("max-w-full", className)}
      style={{ width, height, ...style }}
      {...props}
    />
  );
});

/** antd `<Divider type="vertical|horizontal">`. */
const Divider = React.forwardRef<HTMLDivElement, DividerProps>(function Divider(
  { type = "horizontal", className, children, ...props },
  ref,
) {
  if (children) {
    return (
      <div className={cn("flex items-center gap-2 py-2", className)} {...props}>
        <Separator className="flex-1" />
        <span className="text-sm text-muted-foreground">{children}</span>
        <Separator className="flex-1" />
      </div>
    );
  }
  return (
    <Separator
      ref={ref}
      orientation={type === "vertical" ? "vertical" : "horizontal"}
      className={cn(
        "ant-divider",
        type === "vertical" ? "mx-2 h-auto self-stretch" : "my-2",
        className,
      )}
      {...props}
    />
  );
});

/** antd `<Empty description image />`. */
const Empty = React.forwardRef<HTMLDivElement, EmptyProps>(function Empty(
  { description = "No data", image, className, children, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-8 text-muted-foreground",
        className,
      )}
      {...props}
    >
      {image ?? <Inbox className="size-10 opacity-60" />}
      {description ? <div className="text-sm">{description}</div> : null}
      {children}
    </div>
  );
});

const AVATAR_SIZE = { small: "size-6", default: "size-8", large: "size-10" };

/**
 * antd `<Avatar size shape src icon />`.
 *
 * `inline-flex align-middle`, not the primitive's `flex`. antd's `.ant-avatar`
 * is `display: inline-block`, so `<Avatar /> name` renders on ONE line and
 * call-sites rely on that: Share access and Co-owners both pass
 * `<><Avatar /><Typography.Text /></>` as a single `List.Item.Meta` title and
 * get an avatar stacked ABOVE the email with `flex`, because a block-level box
 * cannot share a line with the text beside it. Blockified inside a flex parent
 * anyway, so rows that already lay their children out are unaffected.
 */
const Avatar = React.forwardRef<HTMLSpanElement, AvatarProps>(function Avatar(
  {
    size = "default",
    shape,
    src,
    icon,
    alt = "",
    className,
    children,
    ...props
  },
  ref,
) {
  const sizeClass =
    typeof size === "number"
      ? undefined
      : (AVATAR_SIZE[size] ?? AVATAR_SIZE.default);

  return (
    <ShadcnAvatar
      ref={ref}
      className={cn(
        "inline-flex align-middle",
        sizeClass,
        shape === "square" && "rounded-md",
        className,
      )}
      style={
        typeof size === "number" ? { width: size, height: size } : undefined
      }
      {...props}
    >
      {src ? <AvatarImage src={src} alt={alt} /> : null}
      <AvatarFallback>{icon ?? children}</AvatarFallback>
    </ShadcnAvatar>
  );
});

/** antd `<Progress percent status />`. */
const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  function Progress(
    { percent = 0, status, showInfo = true, className, ...props },
    ref,
  ) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <ShadcnProgress
          ref={ref}
          value={percent}
          className={cn(
            "flex-1",
            status === "exception" && "[&>div]:bg-destructive",
            status === "success" && "[&>div]:bg-success",
          )}
          {...props}
        />
        {showInfo ? (
          <span className="text-xs text-muted-foreground">
            {Math.round(percent)}%
          </span>
        ) : null}
      </div>
    );
  },
);

export { Alert, Avatar, Divider, Empty, Image, Progress, Spin, Tag };
