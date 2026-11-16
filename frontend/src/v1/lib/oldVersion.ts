/*
 * Storage for the old-version preference (UN-4271, D14): per user, per
 * browser, no backend. Only toggle pages (Human Review) read it.
 */

const KEY_PREFIX = "unstract.v1.oldVersion.";

/** The last user signed in on this browser, so a reload can resolve before the session loads. */
export const LAST_USER_STORAGE_KEY = "unstract.v1.lastUser";

/** The value stored while a user has chosen the old version; absent means v1. */
export const OLD_VERSION_ON = "true";

/** The storage key holding one user's preference. */
export function oldVersionStorageKey(userId: string): string {
  return `${KEY_PREFIX}${userId}`;
}

/** The stored preference; missing or unreadable means v1 (false). */
export function readOldVersion(
  storage: Pick<Storage, "getItem"> | null | undefined,
  userId: string,
): boolean {
  try {
    return storage?.getItem(oldVersionStorageKey(userId)) === OLD_VERSION_ON;
  } catch {
    return false;
  }
}

/** Stores the preference; false if storage is absent or refuses the write. */
export function writeOldVersion(
  storage: Pick<Storage, "setItem" | "removeItem"> | null | undefined,
  userId: string,
  on: boolean,
): boolean {
  if (!storage) {
    return false;
  }
  try {
    const key = oldVersionStorageKey(userId);
    if (on) {
      storage.setItem(key, OLD_VERSION_ON);
    } else {
      storage.removeItem(key);
    }
    return true;
  } catch {
    return false;
  }
}

export function readLastUser(
  storage: Pick<Storage, "getItem"> | null | undefined,
): string | null {
  try {
    return storage?.getItem(LAST_USER_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function writeLastUser(
  storage: Pick<Storage, "setItem"> | null | undefined,
  userId: string,
): void {
  try {
    storage?.setItem(LAST_USER_STORAGE_KEY, userId);
  } catch {
    // Unwritable storage: the next load waits for the session instead.
  }
}
