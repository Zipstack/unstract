import "@v1/styles/index.css";

import { cn } from "@v1/lib/cn";
import { applyThemeMode } from "@v1/lib/portal";
import { selectThemeMode, useThemeStore } from "@v1/stores/theme";
import { type JSX, type ReactNode, useLayoutEffect } from "react";

export type ThemeProviderProps = Readonly<{
  children: ReactNode;
  className?: string;
}>;

const DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";

/** Reading localStorage can throw in sandboxed documents; treat that as no storage. */
function readLocalStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** The v1 root: hydrates the theme store, follows the OS scheme, and stamps the mode. */
export function ThemeProvider({
  children,
  className,
}: ThemeProviderProps): JSX.Element {
  const mode = useThemeStore(selectThemeMode);

  // Layout effect: a saved dark or unstract preference must not paint a light frame first.
  useLayoutEffect(() => {
    const { hydrate, setSystemPrefersDark } = useThemeStore.getState();
    hydrate(readLocalStorage());
    if (typeof window.matchMedia !== "function") {
      return undefined;
    }
    const query = window.matchMedia(DARK_SCHEME_QUERY);
    setSystemPrefersDark(query.matches);
    const onChange = (event: { matches: boolean }) => {
      setSystemPrefersDark(event.matches);
    };
    query.addEventListener("change", onChange);
    return () => {
      query.removeEventListener("change", onChange);
    };
  }, []);

  useLayoutEffect(() => {
    applyThemeMode(document, mode);
  }, [mode]);

  return (
    <div className={cn("v1", className)} data-ui-version="v1" data-theme={mode}>
      {children}
    </div>
  );
}
