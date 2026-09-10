import { Loader2 } from "lucide-react";
import * as React from "react";

import { Button as ShadcnButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * antd-compatible `Button` (P1-04), built on the shadcn primitive.
 *
 * Same reasoning as the Typography shim: antd's Button carries behaviour that
 * shadcn's does not, so a bare find-and-replace would quietly change what the
 * UI does rather than only how it looks (C4). Specifically:
 *
 *   - `loading`  — swaps in a spinner AND disables the button (234 usages)
 *   - `icon`     — renders a leading icon slot (106 usages)
 *   - `danger`   — destructive styling, orthogonal to `type` (12 usages)
 *   - `htmlType` — maps to the DOM `type` attribute, since antd claims `type`
 *                  for its visual variant
 *
 * Presenting antd's API here turns 70 call-site files into an import swap and
 * keeps the JSX untouched. Per D9/§5.0 it lives in OSS so cloud plugins use
 * the same component.
 *
 * New code should prefer `@/components/ui/button` directly; this exists to
 * carry the existing call-sites across without behaviour drift.
 */

/**
 * The antd Button surface this shim accepts.
 *
 * Typing the PROPS is the point of converting this file: the bugs this layer
 * has produced were all silent prop-drops — a prop the call-site passes, the
 * shim never destructures, and `...props` swallows without a warning
 * (`showCount`, `onValuesChange`, `setFields`, `validateStatus`). An explicit
 * surface turns the next one into a compile error at the call-site.
 */
type AntdButtonType = "primary" | "default" | "dashed" | "text" | "link";
type AntdButtonSize = "small" | "middle" | "large";

interface AntdButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  /** antd's visual variant. It claims `type`, so the DOM attribute moves to
   * `htmlType`. */
  type?: AntdButtonType;
  danger?: boolean;
  size?: AntdButtonSize;
  /** Shows a spinner AND disables the button, as antd does. */
  loading?: boolean;
  icon?: React.ReactNode;
  /** The real DOM `type` attribute. */
  htmlType?: "button" | "submit" | "reset";
  block?: boolean;
  shape?: "default" | "circle" | "round";
}

/** antd `type` (+ `danger`) → shadcn variant. */
function toVariant(
  type: AntdButtonType | undefined,
  danger: boolean | undefined,
) {
  if (danger) {
    return type === "text" || type === "link" ? "ghost" : "destructive";
  }
  switch (type) {
    case "primary":
      return "default";
    case "link":
      return "link";
    case "text":
      return "ghost";
    case "dashed":
    case "default":
    default:
      return "outline";
  }
}

/** antd `size` → shadcn size. antd's default sits between sm and lg. */
function toSize(size: AntdButtonSize | undefined, hasOnlyIcon: boolean) {
  if (hasOnlyIcon) {
    return "icon";
  }
  switch (size) {
    case "small":
      return "sm";
    case "large":
      return "lg";
    default:
      return "default";
  }
}

const Button = React.forwardRef<HTMLButtonElement, AntdButtonProps>(
  function Button(
    {
      type,
      danger,
      size,
      loading,
      icon,
      htmlType,
      block,
      shape,
      disabled,
      className,
      children,
      ...props
    },
    ref,
  ) {
    const hasOnlyIcon = Boolean(icon) && !children;

    return (
      <ShadcnButton
        ref={ref}
        variant={toVariant(type, danger)}
        size={toSize(size, hasOnlyIcon)}
        // antd disables the button while loading; preserve that.
        disabled={disabled || Boolean(loading)}
        type={htmlType || "button"}
        className={cn(
          // .ant-btn is targeted by ~9 existing CSS rules (sizing, padding).
          "ant-btn",
          type === "text" && "ant-btn-text",
          block && "w-full",
          shape === "circle" && "rounded-full",
          shape === "round" && "rounded-full",
          // antd's text/link buttons carry no border.
          (type === "text" || type === "link") && "border-0",
          danger && (type === "text" || type === "link") && "text-destructive",
          className,
        )}
        {...props}
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          icon
        )}
        {children}
      </ShadcnButton>
    );
  },
);

export { Button };
