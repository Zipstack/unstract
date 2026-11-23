import { format } from "date-fns";

/* Text for run captions: the timer, the failure time, tokens, cost and time. */

const pad = (n: number) => String(n).padStart(2, "0");

/** Elapsed time as "00:07", or "1:01:05" past an hour. */
export function formatTimer(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(minutes)}:${pad(seconds)}`;
}

/** The time of day a run failed, "14:06:22". */
export function formatClock(epochMs: number): string {
  return format(epochMs, "HH:mm:ss");
}

const NOT_AVAILABLE = "NA";

export function formatTokens(tokens: number | null): string {
  return tokens === null ? NOT_AVAILABLE : tokens.toLocaleString("en-US");
}

/** Dollars to five places, as v0 shows them. */
export function formatCost(dollars: number | null): string {
  return dollars === null
    ? NOT_AVAILABLE
    : `$${dollars.toLocaleString("en-US", {
        minimumFractionDigits: 5,
        maximumFractionDigits: 5,
      })}`;
}

/** Seconds to one place; "0s" when unknown, as v0 shows it. */
export function formatSeconds(seconds: number | null): string {
  return `${seconds === null ? 0 : Math.round(seconds * 10) / 10}s`;
}

/** "request_id: 8f3a-21c9-4d10 · retry after 60s", with only the parts known. */
export function retryHint({
  requestId,
  retryAfterSeconds,
}: Readonly<{
  requestId: string | null;
  retryAfterSeconds: number | null;
}>): string {
  return [
    requestId ? `request_id: ${requestId}` : null,
    retryAfterSeconds === null ? null : `retry after ${retryAfterSeconds}s`,
  ]
    .filter(Boolean)
    .join(" · ");
}
