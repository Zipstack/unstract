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
const TAG_VARIANT = {
  success: "success",
  green: "success",
  warning: "warning",
  orange: "warning",
  gold: "warning",
  error: "destructive",
  red: "destructive",
  processing: "default",
  blue: "default",
  default: "secondary",
};

/** antd `<Tag>`. Custom colours (e.g. `rgb(...)`) fall through to inline style. */
const Tag = React.forwardRef(function Tag(
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
  const variant = color ? TAG_VARIANT[color] : "secondary";
  // A raw CSS colour antd would have applied directly.
  const custom = color && !TAG_VARIANT[color] ? color : undefined;

  return (
    <Badge
      ref={ref}
      variant={variant ?? "secondary"}
      className={cn("gap-1", className)}
      style={
        custom
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
          className="ml-0.5"
        >
          <X className="size-3" />
        </button>
      ) : null}
    </Badge>
  );
});

/** antd `<Spin>`. Only the bare indicator form is used in this codebase. */
const Spin = React.forwardRef(function Spin(
  { size, tip, className, ...props },
  ref,
) {
  const mapped = size === "large" ? "lg" : size === "small" ? "sm" : "default";
  return (
    <span
      ref={ref}
      className={cn("inline-flex items-center gap-2", className)}
      {...props}
    >
      <Spinner size={mapped} />
      {tip ? (
        <span className="text-sm text-muted-foreground">{tip}</span>
      ) : null}
    </span>
  );
});

const ALERT_ICON = {
  success: CircleCheck,
  info: Info,
  warning: TriangleAlert,
  error: CircleAlert,
};

/** antd `<Alert message description type showIcon closable banner />`. */
const Alert = React.forwardRef(function Alert(
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
          className="absolute right-3 top-3"
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
const Image = React.forwardRef(function Image(
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
const Divider = React.forwardRef(function Divider(
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
        type === "vertical" ? "mx-2 h-auto self-stretch" : "my-2",
        className,
      )}
      {...props}
    />
  );
});

/** antd `<Empty description image />`. */
const Empty = React.forwardRef(function Empty(
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

/** antd `<Avatar size shape src icon />`. */
const Avatar = React.forwardRef(function Avatar(
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
      className={cn(sizeClass, shape === "square" && "rounded-md", className)}
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
const Progress = React.forwardRef(function Progress(
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
});

export { Tag, Spin, Alert, Image, Divider, Empty, Avatar, Progress };
