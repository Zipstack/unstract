/**
 * The notification contract: the one way v1 tells the user something happened.
 *
 * It lives in `lib/` so every folder can reach it, including `services/`, which
 * may import only `lib/` (the P0-T05 error normaliser is meant to call
 * `notify()`), and the `Toaster` in `components/ui/feedback/` registers itself
 * as the notifier. No
 * other toast library may be imported in v1 (`lint:v1` enforces it).
 */

export const NOTIFY_KINDS = ["success", "error", "warning", "info"] as const;
export type NotifyKind = (typeof NOTIFY_KINDS)[number];

export type NotifyAction = Readonly<{
  /** The button text; also its accessible name. */
  label: string;
  onSelect: () => void;
}>;

export type NotifyInput = Readonly<{
  kind: NotifyKind;
  title: string;
  description?: string;
  action?: NotifyAction;
  /**
   * Stays until the user dismisses it; otherwise it times out. At the stack
   * limit, timed toasts are dropped before persistent ones.
   */
  persistent?: boolean;
  /** The backend request id, shown (and selectable) on the toast for support. */
  requestId?: string;
  /**
   * Reusing an id replaces the open notification instead of stacking another;
   * the replacement starts its own timer and is announced again.
   */
  id?: string;
}>;

export type Notifier = Readonly<{
  /** Shows the notification and returns its id. */
  show: (input: NotifyInput) => string;
  dismiss: (id: string) => void;
}>;

let current: Notifier | null = null;

/** Registers the notifier; returns a cleanup that unregisters only this one. */
export function setNotifier(notifier: Notifier): () => void {
  current = notifier;
  return () => {
    if (current === notifier) {
      current = null;
    }
  };
}

const FALLBACK_LOG: Record<NotifyKind, "error" | "warn" | "info"> = {
  error: "error",
  warning: "warn",
  success: "info",
  info: "info",
};

/**
 * Tells the user something happened. With no notifier mounted (a test, or a
 * failure before the app shell renders) the message is only logged to the
 * console with its request id: it is not shown, not queued for a later mount,
 * and its action is lost. Callers that must reach the user before the shell
 * renders need their own fallback.
 */
export function notify(input: NotifyInput): string | undefined {
  if (current) {
    return current.show(input);
  }
  const parts = [input.title, input.description].filter(Boolean).join(": ");
  const trace = input.requestId ? ` (request ${input.requestId})` : "";
  // The documented fallback: logged to the console, not shown.
  console[FALLBACK_LOG[input.kind]](`[v1 notify] ${parts}${trace}`);
  return undefined;
}

export function dismissNotification(id: string): void {
  current?.dismiss(id);
}

type Shorthand = Omit<NotifyInput, "kind" | "title">;

/** Shorthands for `notify()`, one per kind. */
export const toast = {
  success: (title: string, rest?: Shorthand) =>
    notify({ ...rest, kind: "success", title }),
  error: (title: string, rest?: Shorthand) =>
    notify({ ...rest, kind: "error", title }),
  warning: (title: string, rest?: Shorthand) =>
    notify({ ...rest, kind: "warning", title }),
  info: (title: string, rest?: Shorthand) =>
    notify({ ...rest, kind: "info", title }),
  dismiss: dismissNotification,
} as const;
