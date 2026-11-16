/**
 * Browser storage cleanup at logout.
 *
 * Logging out must not leave the user's data behind in the browser: the
 * dashboard metrics cache, connector OAuth state and the last signed-in user
 * all live in localStorage or sessionStorage. Everything is removed except
 * the UI preferences below, which say nothing about the user or their data
 * and would otherwise reset on every logout.
 */

const KEPT_LOCAL_STORAGE_KEYS = new Set([
  "selectedProduct",
  "collapsed",
  "sidebarPinned",
  "unstract.v1.theme",
  "unstract.v1.preview",
]);

// One entry per user who chose the old version on this browser (UN-4271).
const KEPT_LOCAL_STORAGE_PREFIXES = ["unstract.v1.oldVersion."];

const isKept = (key) =>
  KEPT_LOCAL_STORAGE_KEYS.has(key) ||
  KEPT_LOCAL_STORAGE_PREFIXES.some((prefix) => key.startsWith(prefix));

export const clearBrowserStorage = () => {
  try {
    window.sessionStorage.clear();
  } catch {
    // Storage unavailable (sandboxed document): nothing to clear.
  }
  try {
    const storage = window.localStorage;
    // Collect first: removing while iterating by index shifts the indices.
    const keys = [];
    for (let i = 0; i < storage.length; i++) {
      keys.push(storage.key(i));
    }
    for (const key of keys) {
      if (key !== null && !isKept(key)) {
        storage.removeItem(key);
      }
    }
  } catch {
    // Storage unavailable (sandboxed document): nothing to clear.
  }
};
