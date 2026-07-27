import { toast } from "sonner";

/**
 * Shared toast surface for the whole app (OSS-owned, per D9 / §5.0).
 *
 * Cloud plugins MUST import this rather than calling `sonner` directly or
 * reimplementing their own toast helper — that is what keeps the notification
 * behaviour identical across OSS and enterprise code.
 *
 * During P0–P2 this runs alongside antd's `notification` (§7 coexistence):
 * `useAlertStore` drives both, and antd's imperative `message.*` /
 * `notification.*` call-sites are migrated onto this helper in P2-06.
 */

/** antd alert types → the matching sonner method. */
const TOAST_BY_TYPE = {
  success: toast.success,
  error: toast.error,
  warning: toast.warning,
  info: toast.info,
};

/**
 * Show a toast from an `alertDetails`-shaped object.
 *
 * @param {object} details             alert payload
 * @param {string} details.type        "success" | "error" | "warning" | "info"
 * @param {string} details.title       heading
 * @param {string} details.content     body text
 * @param {number} [details.duration]  seconds (antd convention; 0 = sticky)
 * @param {string} [details.key]       dedupe/dismiss id
 * @param {string} [details.requestId]
 * @param {string} [details.executionId]
 * @returns {string|number|undefined} the sonner toast id
 */
export function showAppToast(details, description) {
  if (!details?.content && !details?.title) {
    return undefined;
  }

  const show = TOAST_BY_TYPE[details.type] ?? toast;

  // antd expresses duration in seconds and treats 0 as "never auto-dismiss";
  // sonner uses milliseconds and Infinity.
  const duration =
    details.duration === 0
      ? Number.POSITIVE_INFINITY
      : (details.duration ?? 6) * 1000;

  const idLine = [
    details.executionId && `Execution ID: ${details.executionId}`,
    details.requestId && `Request ID: ${details.requestId}`,
  ]
    .filter(Boolean)
    .join("\n");

  return show(details.title || details.content, {
    // A React node (rendered markdown + ID lines) wins over the plain string
    // when the caller supplies one — that is how App.jsx keeps the formatted
    // alert body it previously handed to antd's notification.
    description:
      description ??
      (idLine ? `${details.content ?? ""}\n${idLine}`.trim() : details.content),
    duration,
    id: details.key,
  });
}

/** Dismiss one toast by id, or all toasts when called with no argument. */
export function dismissAppToast(id) {
  toast.dismiss(id);
}

/** Hook form, for call-sites that prefer a hook over the bare functions. */
export function useAppToast() {
  return { showAppToast, dismissAppToast, toast };
}

/**
 * Drop-in replacement for antd's imperative `message.*` API (P2-06).
 *
 * antd's `message.error("…")` is a bare function call with no React context,
 * which is exactly what `sonner` provides too — so these call-sites convert by
 * import alone. Kept API-compatible (including the seconds→ms duration
 * convention) so the ~12 sites did not each need rewriting.
 */
export const message = {
  success: (content, duration) =>
    toast.success(content, { duration: toMs(duration) }),
  error: (content, duration) =>
    toast.error(content, { duration: toMs(duration) }),
  warning: (content, duration) =>
    toast.warning(content, { duration: toMs(duration) }),
  info: (content, duration) =>
    toast.info(content, { duration: toMs(duration) }),
  loading: (content) => toast.loading(content),
  open: (content, duration) => toast(content, { duration: toMs(duration) }),
  destroy: (id) => toast.dismiss(id),
};

/** antd counts duration in seconds (0 = sticky); sonner uses milliseconds. */
function toMs(duration) {
  if (duration === 0) {
    return Number.POSITIVE_INFINITY;
  }
  return duration == null ? undefined : duration * 1000;
}

/**
 * Drop-in replacement for antd's imperative `notification.*` API (P2-06 /
 * Phase C). antd's notification takes `{ message, description }`; sonner takes
 * a title plus `{ description }`, so the shape is remapped here rather than at
 * each call-site.
 */
export const notification = {
  success: (cfg = {}) =>
    showAppToast({
      ...cfg,
      type: "success",
      title: cfg.message,
      content: cfg.description,
    }),
  error: (cfg = {}) =>
    showAppToast({
      ...cfg,
      type: "error",
      title: cfg.message,
      content: cfg.description,
    }),
  warning: (cfg = {}) =>
    showAppToast({
      ...cfg,
      type: "warning",
      title: cfg.message,
      content: cfg.description,
    }),
  info: (cfg = {}) =>
    showAppToast({
      ...cfg,
      type: "info",
      title: cfg.message,
      content: cfg.description,
    }),
  open: (cfg = {}) =>
    showAppToast({ ...cfg, title: cfg.message, content: cfg.description }),
  destroy: (key) => dismissAppToast(key),
  /** antd exposes a hook form returning [api, contextHolder]. */
  useNotification: () => [notification, null],
};
