/*
 * Browser storage cleanup when a session ends, for v1 sign-out and (through
 * `@v1`) v0's logout and expired-session paths.
 *
 * A session must not leave the user's data in the browser (connector OAuth
 * state, the last signed-in user). Everything goes except UI preferences that
 * say nothing about the user or their data.
 *
 * Other open tabs are told too: they still show the user's data and hold it
 * in their own sessionStorage, so on a sign-out elsewhere they clear it and
 * sign out themselves.
 */

const SIGNED_OUT = "signed-out";

// One channel per document for both sending and listening: a BroadcastChannel
// never receives its own messages, so the tab signing out does not react to
// its own announcement.
let channel: BroadcastChannel | null | undefined;

function sessionChannel(): BroadcastChannel | null {
  if (channel === undefined) {
    channel =
      typeof BroadcastChannel === "undefined"
        ? null
        : new BroadcastChannel("unstract.session");
  }
  return channel;
}

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

/** Removes every localStorage key except the preferences above. */
export function clearUserLocalStorage(): void {
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

/**
 * At sign-out: all of sessionStorage, and localStorage bar the preferences.
 * Tells the other open tabs, which then clear theirs and sign out too.
 */
export function clearBrowserStorage(): void {
  try {
    window.sessionStorage.clear();
  } catch {
    // Storage unavailable (sandboxed document): nothing to clear.
  }
  clearUserLocalStorage();
  try {
    sessionChannel()?.postMessage(SIGNED_OUT);
  } catch {
    // A closed or unsupported channel: other tabs find out on their next
    // request instead.
  }
}

/**
 * When another tab signs out, clears this tab's sessionStorage and signs this
 * tab out too. Mount once at the app root; returns the unsubscribe.
 *
 * It signs out rather than reloads: the message can arrive before the server
 * has ended the session (v0 logs out by navigating to the GET logout, and v1
 * falls back to it when the POST fails), and a reload that wins that race
 * would load the user's data again. Logging out again is harmless, so
 * whichever request reaches the server first ends the session.
 */
export function signOutWhenSignedOutElsewhere(): () => void {
  const current = sessionChannel();
  if (!current) {
    return () => undefined;
  }
  const onMessage = (event: MessageEvent) => {
    if (event.data !== SIGNED_OUT) {
      return;
    }
    try {
      window.sessionStorage.clear();
    } catch {
      // Storage unavailable: leaving the page still removes the data on screen.
    }
    window.location.assign("/api/v1/logout");
  };
  current.addEventListener("message", onMessage);
  return () => current.removeEventListener("message", onMessage);
}
