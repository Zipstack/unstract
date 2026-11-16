import type { NotifyKind } from "@v1/lib/notify";
import {
  CircleAlert,
  CircleCheck,
  Info,
  type LucideIcon,
  TriangleAlert,
} from "lucide-react";

/** The icon and its colour for each kind, shared by toasts and inline alerts. */
export const KIND_ICON: Record<NotifyKind, LucideIcon> = {
  success: CircleCheck,
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
};

// There is no `info` token yet; `primary` stands in until the designer adds one.
export const KIND_TEXT: Record<NotifyKind, string> = {
  success: "ui:text-success",
  error: "ui:text-destructive",
  warning: "ui:text-warning",
  info: "ui:text-primary",
};

export const KIND_BORDER: Record<NotifyKind, string> = {
  success: "ui:border-success",
  error: "ui:border-destructive",
  warning: "ui:border-warning",
  info: "ui:border-primary",
};
