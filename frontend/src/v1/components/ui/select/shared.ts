import type { RefObject } from "react";

/*
 * Pieces shared by the popover-list fields (Combobox, MultiSelect), whose
 * focus stays in an input inside the frame while the list is open.
 */

/** An icon button inside the frame (clear, chevron). */
export const ICON_BUTTON =
  "ui:flex ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-md ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:hover:text-foreground ui:focus-visible:focus-ring ui:disabled:pointer-events-none";

/** Whether `target` (a blur's `relatedTarget`) is inside the frame or the list. */
export function isInside(
  frame: HTMLElement | null,
  content: HTMLElement | null,
  target: EventTarget | null,
): boolean {
  return (
    target instanceof Node &&
    Boolean(frame?.contains(target) || content?.contains(target))
  );
}

/**
 * Props for the list's `Popover.Content`: no dialog role (the listbox inside
 * is the popup), focus never moves into or back from it, a press inside the
 * frame is not outside, and a press on the list's padding keeps focus in the
 * input.
 */
export function listContentProps(frameRef: RefObject<HTMLElement | null>) {
  return {
    role: "presentation",
    onOpenAutoFocus: (event: Event) => event.preventDefault(),
    onCloseAutoFocus: (event: Event) => event.preventDefault(),
    onInteractOutside: (event: Event) => {
      const target = event.target;
      if (target instanceof Node && frameRef.current?.contains(target)) {
        event.preventDefault();
      }
    },
    onMouseDown: (event: { preventDefault: () => void }) =>
      event.preventDefault(),
  } as const;
}
