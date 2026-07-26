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
export function showAppToast(details) {
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
    description: idLine
      ? `${details.content ?? ""}\n${idLine}`.trim()
      : details.content,
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
