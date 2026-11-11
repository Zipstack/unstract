import type { KeyboardEvent } from "react";

/*
 * True while an IME composition owns the key. Safari fires the keydown that
 * ends a composition after compositionend, with isComposing already false;
 * keyCode 229 is the only mark it leaves.
 */
export function isComposing(event: KeyboardEvent): boolean {
  return event.nativeEvent.isComposing || event.keyCode === 229;
}

/**
 * For an overlay's `onEscapeKeyDown` (Dialog, Popover, Menu): true when the
 * Escape belongs to a SearchField that will clear its value, so the overlay
 * calls `preventDefault()` and stays open. Radix sees Escape on the document
 * in the capture phase, before the field does, so the overlay must ask.
 */
export function isEscapeClearTarget(event: Event): boolean {
  return (
    event.target instanceof Element &&
    event.target.closest("[data-escape-clears]") !== null
  );
}
