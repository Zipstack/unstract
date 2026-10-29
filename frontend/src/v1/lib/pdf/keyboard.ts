/** What a key does in the document viewer, when the viewer has focus. */
export type ViewerKeyAction =
  | "previous-page"
  | "next-page"
  | "first-page"
  | "last-page"
  | "zoom-in"
  | "zoom-out";

/**
 * Maps a key to a viewer action. Keys pressed with Ctrl, Meta or Alt are left
 * to the browser, so its own zoom and shortcuts keep working.
 */
export function viewerKeyAction(event: {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
}): ViewerKeyAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey) {
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
