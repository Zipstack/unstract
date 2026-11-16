/*
 * Browser storage cleanup at sign-out. Mirrors v0's clearBrowserStorage
 * (src/helpers/clearBrowserStorage.js), which v1 may not import; change both
 * allowlists together.
 *
 * Signing out must not leave the user's data in the browser (the dashboard
 * metrics cache, connector OAuth state, the last signed-in user). Everything
 * goes except UI preferences that say nothing about the user or their data.
 */

const KEPT_KEYS: ReadonlySet<string> = new Set([
  "selectedProduct",
  "collapsed",
  "sidebarPinned",
  "unstract.v1.theme",
  "unstract.v1.preview",
  // Enterprise plugins: dismissed-banner flags.
  "aps_onboarding_stepper_dismissed",
  "unstract_welcome_card_dismissed",
]);

// One entry per user who chose the old version on this browser (UN-4271).
const KEPT_PREFIXES: readonly string[] = ["unstract.v1.oldVersion."];

function isKept(key: string): boolean {
  return KEPT_KEYS.has(key) || KEPT_PREFIXES.some((p) => key.startsWith(p));
}

/** Clears sessionStorage, and localStorage except the preferences above. */
export function clearBrowserStorage(): void {
  try {
    window.sessionStorage.clear();
  } catch {
    // Storage unavailable (sandboxed document): nothing to clear.
  }
  try {
    const storage = window.localStorage;
    // Collect first: removing while iterating by index shifts the indices.
    const keys: string[] = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key !== null) {
        keys.push(key);
      }
    }
    for (const key of keys) {
      if (!isKept(key)) {
        storage.removeItem(key);
      }
    }
  } catch {
    // Storage unavailable (sandboxed document): nothing to clear.
  }
}
