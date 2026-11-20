import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

// The one way to confirm: one request on screen at a time, the rest queue.

type ConfirmBase = Readonly<{
  /** The question; it names the dialog. */
  title: string;
  /** A panel under the text, e.g. the items affected. */
  details?: ReactNode;
  /** The glyph in the header chip. */
  icon?: LucideIcon;
}>;

type ConfirmAction = Readonly<{
  /** What happens, under the title. */
  description?: ReactNode;
  /** The action button's label, a verb: "Delete deployment". */
  confirmLabel: string;
  confirmIcon?: LucideIcon;
  /** Default "Cancel". */
  cancelLabel?: string;
  /** Runs while the dialog shows busy; a throw keeps the dialog open. */
  action?: () => Promise<void>;
}>;

export type StandardConfirm = ConfirmBase &
  ConfirmAction &
  Readonly<{ tone?: "standard" }>;

export type DestructiveConfirm = ConfirmBase &
  ConfirmAction &
  Readonly<{
    tone: "destructive";
    /** The red note, e.g. "This cannot be undone." */
    consequence: ReactNode;
  }>;

export type BlockedConfirm = ConfirmBase &
  Readonly<{
    tone: "blocked";
    /** Why it cannot proceed, and what to do first. */
    reason: ReactNode;
    /** A way to fix it, e.g. "Open project"; it closes the dialog. */
    link?: Readonly<{ label: string; onSelect: () => void }>;
    /** Default "Close". */
    closeLabel?: string;
  }>;

export type ConfirmOptions =
  | StandardConfirm
  | DestructiveConfirm
  | BlockedConfirm;

export type ConfirmRequest = Readonly<{ id: number; options: ConfirmOptions }>;

type Pending = ConfirmRequest & Readonly<{ resolve: (ok: boolean) => void }>;

let queue: readonly Pending[] = [];
let listener: (() => void) | null = null;
let nextId = 1;

function setQueue(next: readonly Pending[]): void {
  queue = next;
  listener?.();
}

/**
 * Resolves true when the user confirms; any other close, and every blocked
 * request, resolves false. With no host mounted it resolves false and warns.
 */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  if (!listener) {
    console.warn("[v1 confirm] no ConfirmHost mounted: %s", options.title);
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    setQueue([...queue, { id: nextId++, options, resolve }]);
  });
}

/** The request on screen, or null. */
export function currentConfirm(): ConfirmRequest | null {
  return queue[0] ?? null;
}

/** Answers the request on screen and shows the next; a blocked one is always false. */
export function settleConfirm(id: number, ok: boolean): void {
  const head = queue[0];
  if (head?.id !== id) {
    return;
  }
  head.resolve(ok && head.options.tone !== "blocked");
  setQueue(queue.slice(1));
}

/** The host's subscription; unsubscribing answers every waiting request false. */
export function subscribeConfirm(onChange: () => void): () => void {
  listener = onChange;
  return () => {
    if (listener !== onChange) {
      return;
    }
    listener = null;
    const pending = queue;
    queue = [];
    for (const entry of pending) {
      entry.resolve(false);
    }
  };
}
