import { notify } from "@v1/lib/notify";
import { isCancelled, toApiError } from "./errors";

export type ReportOptions = Readonly<{
  /** False when the caller shows the error itself; it is then only logged. */
  notify?: boolean;
  /** Reusing an id replaces the open toast instead of stacking another. */
  id?: string;
}>;

/**
 * Reports a failed request: a toast through notify(), or a log line with its
 * request id when the caller shows it. Cancellations and session expiry
 * (already redirected) report nothing.
 */
export function reportApiError(
  error: unknown,
  options: ReportOptions = {},
): void {
  if (isCancelled(error)) {
    return;
  }
  const apiError = toApiError(error);
  if (apiError.kind === "unauthenticated") {
    return;
  }
  if (apiError.kind === "unknown") {
    console.error("[v1 api] unexpected failure", apiError.cause);
  }
  if (options.notify === false) {
    const requestId = apiError.requestId ?? "none";
    console.warn("[v1 api] %s (request %s)", apiError.message, requestId);
    return;
  }
  notify({
    kind: "error",
    title: apiError.message,
    requestId: apiError.requestId,
    persistent: apiError.kind === "subscription",
    id: options.id,
  });
}
