import {
  readLastUser,
  readOldVersion,
  writeLastUser,
  writeOldVersion,
} from "@v1/lib/oldVersion";
import { create, type UseBoundStore } from "zustand";
import { createStore, type StateCreator, type StoreApi } from "zustand/vanilla";

export type OldVersionState = {
  /** The user the preference belongs to: the signed-in user, else the last one on this browser. */
  userId: string | null;
  /** That user's choice; null while no user is known. Only toggle pages read it. */
  oldVersion: boolean | null;
  /** Choices made this session, so they hold when storage refuses the write. */
  chosen: Readonly<Record<string, boolean>>;
  /** Follows the signed-in user. Signing out (null) keeps the last user. */
  setUser: (userId: string | null) => void;
  /**
   * Sets the current user's choice and saves it to localStorage. The version
   * switch then moves the user to the equivalent screen, with no reload.
   * True once the choice is set, even if storage refused the write: then it
   * lasts for this session only. False (and no change) while no user is known.
   */
  setOldVersion: (on: boolean) => boolean;
};

type PreferenceStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
> | null;

function oldVersionState(
  storage: PreferenceStorage,
): StateCreator<OldVersionState> {
  const lastUser = readLastUser(storage);
  return (set, get) => ({
    userId: lastUser,
    oldVersion: lastUser === null ? null : readOldVersion(storage, lastUser),
    chosen: {},
    setUser: (userId) => {
      if (userId === null || userId === get().userId) {
        return;
      }
      writeLastUser(storage, userId);
      set((state) => ({
        userId,
        oldVersion: state.chosen[userId] ?? readOldVersion(storage, userId),
      }));
    },
    setOldVersion: (on) => {
      const { userId } = get();
      if (userId === null) {
        return false;
      }
      writeOldVersion(storage, userId, on);
      set((state) => ({
        oldVersion: on,
        chosen: { ...state.chosen, [userId]: on },
      }));
      return true;
    },
  });
}

/** A standalone store, for tests and isolated trees. */
export function createOldVersionStore(
  storage: PreferenceStorage = null,
): StoreApi<OldVersionState> {
  return createStore<OldVersionState>()(oldVersionState(storage));
}

/** Reading localStorage can throw in sandboxed documents; treat that as no storage. */
function browserStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const useOldVersionStore: UseBoundStore<StoreApi<OldVersionState>> =
  create<OldVersionState>()(oldVersionState(browserStorage()));
