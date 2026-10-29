/**
 * The provider key of an adapter or connector id: the part before `|`
 * (`openai|502ecf49-…` → `openai`). An id without `|` is its own key.
 */
export function providerKey(id: string): string {
  return id.split("|", 1)[0].trim();
}

/**
 * The API's `icon` field as a usable image source, or null. Unresolvable
 * adapters send the string "⚠️" (AdapterKeys.UNAVAILABLE_ICON), so anything
 * that is not a path or an http(s) or data:image URL counts as missing.
 */
export function iconSource(icon: string | null | undefined): string | null {
  const value = icon?.trim();
  if (!value) {
    return null;
  }
  return /^(\/|https?:\/\/|data:image\/)/.test(value) ? value : null;
}
