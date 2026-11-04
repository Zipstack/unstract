import { DEFAULT_THEME_MODE, THEME_MODES, type ThemeMode } from "./theme";

/** The single element under <body> that v1 dialogs, menus and toasts render into. */
export const PORTAL_CONTAINER_ID = "v1-portal";

/** The class that scopes v1 styles; every element carrying it gets a data-theme. */
export const V1_ROOT_CLASS = "v1";

function isThemeMode(value: string | undefined): value is ThemeMode {
  return (THEME_MODES as readonly (string | undefined)[]).includes(value);
}

/** The mode already shown by a v1 root, so a late-created container matches it. */
function currentThemeMode(doc: Document): ThemeMode {
  const root = doc.querySelector<HTMLElement>(`.${V1_ROOT_CLASS}[data-theme]`);
  const theme = root?.dataset.theme;
  return isThemeMode(theme) ? theme : DEFAULT_THEME_MODE;
}

/** Returns the portal container, creating it under <body> on first use. */
export function getPortalContainer(doc: Document = document): HTMLElement {
  const existing = doc.getElementById(PORTAL_CONTAINER_ID);
  if (existing) {
    return existing;
  }
  const container = doc.createElement("div");
  container.id = PORTAL_CONTAINER_ID;
  container.className = V1_ROOT_CLASS;
  container.dataset.theme = currentThemeMode(doc);
  doc.body.appendChild(container);
  return container;
}

/** Stamps the mode on every v1 element: the app roots and the portal container. */
export function applyThemeMode(doc: Document, mode: ThemeMode): void {
  for (const element of doc.querySelectorAll<HTMLElement>(
    `.${V1_ROOT_CLASS}`,
  )) {
    element.dataset.theme = mode;
  }
}
