import {
  readThemePreference,
  resolveThemeMode,
  type ThemeMode,
  type ThemePreference,
  writeThemePreference,
} from "@v1/lib/theme";
import { create, type UseBoundStore } from "zustand";
import { createStore, type StateCreator, type StoreApi } from "zustand/vanilla";

export type ThemeState = {
  preference: ThemePreference;
  systemPrefersDark: boolean;
  /** Always resolveThemeMode(preference, systemPrefersDark). */
  mode: ThemeMode;
  /** Sets the preference and persists it; a refused write is ignored. */
  setPreference: (preference: ThemePreference) => void;
  setSystemPrefersDark: (value: boolean) => void;
  /** Replaces the preference with the one in storage ("system" if none). */
  hydrate: (storage: Pick<Storage, "getItem"> | null | undefined) => void;
};

export type ThemeStoreOptions = {
  storage?: Pick<Storage, "getItem" | "setItem"> | null;
  systemPrefersDark?: boolean;
};

/** Theme state only; the DOM is updated by whoever subscribes (ThemeProvider). */
function themeState({
  storage = null,
  systemPrefersDark = false,
}: ThemeStoreOptions): StateCreator<ThemeState> {
  return (set) => ({
    preference: "system",
    systemPrefersDark,
    mode: resolveThemeMode("system", systemPrefersDark),
    setPreference: (preference) => {
      writeThemePreference(storage, preference);
      set((state) => ({
        preference,
        mode: resolveThemeMode(preference, state.systemPrefersDark),
      }));
    },
    setSystemPrefersDark: (value) => {
      set((state) => ({
        systemPrefersDark: value,
        mode: resolveThemeMode(state.preference, value),
      }));
    },
    hydrate: (source) => {
      const preference = readThemePreference(source);
      set((state) => ({
        preference,
        mode: resolveThemeMode(preference, state.systemPrefersDark),
      }));
    },
  });
}

/** A standalone store, for tests and isolated trees. */
export function createThemeStore(
  options: ThemeStoreOptions = {},
): StoreApi<ThemeState> {
  return createStore<ThemeState>()(themeState(options));
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

/** The app's theme store; the provider binds the real prefers-color-scheme query. */
export const useThemeStore: UseBoundStore<StoreApi<ThemeState>> =
  create<ThemeState>()(
    themeState({ storage: browserStorage(), systemPrefersDark: false }),
  );

export const selectThemeMode = (s: ThemeState) => s.mode;
export const selectThemePreference = (s: ThemeState) => s.preference;
