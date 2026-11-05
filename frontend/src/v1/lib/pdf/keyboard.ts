/** What a key does in the document viewer, when the viewer has focus. */
export type ViewerKeyAction =
  | "previous-page"
  | "next-page"
  | "first-page"
  | "last-page"
  | "zoom-in"
  | "zoom-out";

const TEXT_FIELDS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** Whether a key pressed here belongs to a field the user is typing in. */
function isEditable(target: unknown): boolean {
  if (typeof target !== "object" || target === null) {
    return false;
  }
  const element = target as { tagName?: unknown; isContentEditable?: unknown };
  return (
    element.isContentEditable === true ||
    (typeof element.tagName === "string" && TEXT_FIELDS.has(element.tagName))
  );
}

/**
 * Maps a key to a viewer action. Keys pressed with Ctrl, Meta or Alt are left
 * to the browser, so its own zoom and shortcuts keep working, and keys typed
 * into a field (an input, textarea, select or contenteditable drawn over the
 * pages) stay with the field.
 */
export function viewerKeyAction(event: {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  target?: unknown;
}): ViewerKeyAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey) {
    return null;
  }
  if (isEditable(event.target)) {
    return null;
  }
  switch (event.key) {
    case "PageUp":
      return "previous-page";
    case "PageDown":
      return "next-page";
    case "Home":
      return "first-page";
    case "End":
      return "last-page";
    case "+":
    case "=":
      return "zoom-in";
    case "-":
    case "_":
      return "zoom-out";
    default:
      return null;
  }
}
