import type { KeyboardEvent } from "react";

/*
 * True while an IME composition owns the key. Safari fires the keydown that
 * ends a composition after compositionend, with isComposing already false;
 * keyCode 229 is the only mark it leaves.
 */
export function isComposing(event: KeyboardEvent): boolean {
  return event.nativeEvent.isComposing || event.keyCode === 229;
}
