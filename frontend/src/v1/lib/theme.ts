/** A colour mode the v1 shell can render. */
export type ThemeMode = "light" | "dark" | "unstract";

/** What the user chose: a fixed mode, or follow the operating system. */
export type ThemePreference = ThemeMode | "system";

export const THEME_MODES: readonly ThemeMode[] = ["light", "dark", "unstract"];

/** v1's own storage key; v0 (next-themes) uses `theme`, which v1 never reads. */
export const THEME_STORAGE_KEY = "unstract.v1.theme";

export const DEFAULT_THEME_MODE: ThemeMode = "light";

const SYSTEM_PREFERENCE: ThemePreference = "system";

export function isThemePreference(value: unknown): value is ThemePreference {
  return (
    value === SYSTEM_PREFERENCE ||
    (THEME_MODES as readonly unknown[]).includes(value)
  );
}

export function resolveThemeMode(
  preference: ThemePreference,
  systemPrefersDark: boolean,
): ThemeMode {
  if (preference !== "system") {
    return preference;
  }
  return systemPrefersDark ? "dark" : DEFAULT_THEME_MODE;
}

/** Reads the stored preference; any missing, unknown or unreadable value means "system". */
export function readThemePreference(
  storage: Pick<Storage, "getItem"> | null | undefined,
): ThemePreference {
  if (!storage) {
    return SYSTEM_PREFERENCE;
  }
  try {
    const stored = storage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : SYSTEM_PREFERENCE;
  } catch {
    return SYSTEM_PREFERENCE;
  }
}

/** Stores the preference; storage that is absent or refuses the write is ignored. */
export function writeThemePreference(
  storage: Pick<Storage, "setItem"> | null | undefined,
  preference: ThemePreference,
): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Private mode or a full quota: the preference simply does not persist.
  }
}
