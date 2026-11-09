/**
 * What a copy attempt did: `copied`, `unavailable` (no Clipboard API, as on a
 * page served over plain HTTP from a non-localhost host) or `failed` (the
 * browser refused, for example without permission or focus).
 */
export type CopyResult = "copied" | "unavailable" | "failed";

/** Writes `text` to the clipboard; never throws. */
export async function copyText(text: string): Promise<CopyResult> {
  const clipboard =
    typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (typeof clipboard?.writeText !== "function") {
    return "unavailable";
  }
  try {
    await clipboard.writeText(text);
    return "copied";
  } catch {
    return "failed";
  }
}
