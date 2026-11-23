import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

// The one way to confirm: one request on screen at a time.

/** Text that must render: no null, undefined or boolean. */
type Text = Exclude<ReactNode, null | undefined | boolean>;

type ConfirmBase = Readonly<{
  /** The question; it names the dialog. */
  title: string;
  /** A panel under the text, e.g. the items affected. */
  details?: ReactNode;
  /** The glyph in the header chip. */
  icon?: LucideIcon;
}>;

type ConfirmAction = Readonly<{
  /** What happens, under the title; it describes the dialog. */
  description: Text;
  /** The action button's label, a verb: "Delete deployment". */
  confirmLabel: string;
  confirmIcon?: LucideIcon;
  /** Default "Cancel". */
  cancelLabel?: string;
  /** Runs while the dialog shows busy; a throw keeps the dialog open. */
  action?: () => Promise<void>;
}>;

// Without a tone, another tone's fields must not compile as a standard confirm.
export type StandardConfirm = ConfirmBase &
  ConfirmAction &
  Readonly<{
    tone?: "standard";
    consequence?: never;
    reason?: never;
    link?: never;
    closeLabel?: never;
  }>;

export type DestructiveConfirm = ConfirmBase &
  ConfirmAction &
  Readonly<{
    tone: "destructive";
    /** The red note, e.g. "This cannot be undone." */
    consequence: Text;
  }>;

export type BlockedConfirm = ConfirmBase &
  Readonly<{
    tone: "blocked";
    /** Why it cannot proceed, and what to do first. */
    reason: Text;
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
let runningId: number | null = null;
let nextId = 1;

function setQueue(next: readonly Pending[]): void {
  queue = next;
  listener?.();
}

/** Marks request `id`'s `action` as running or ended; an end for another request is ignored. */
export function setConfirmRunning(id: number, value: boolean): void {
  if (value) {
    runningId = id;
  } else if (runningId === id) {
    runningId = null;
  }
}

// A host that mounts in the same commit as the caller subscribes after its effects.
function dropIfNoHost(): void {
  if (listener) {
    return;
  }
  const pending = queue;
  queue = [];
  for (const entry of pending) {
    console.warn(
      "[v1 confirm] no ConfirmHost mounted: %s",
      entry.options.title,
    );
    entry.resolve(false);
  }
}

/**
 * Resolves true when the user confirms; any other close, and every blocked
 * request, resolves false. With no host by the next task it resolves false
 * and warns.
 */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  // Only while the request on screen is running: a host that unmounted mid-action leaves none.
  if (runningId !== null && queue[0]?.id === runningId) {
    console.error(
      "[v1 confirm] called while an action runs: %s",
      options.title,
    );
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    setQueue([...queue, { id: nextId++, options, resolve }]);
    if (!listener) {
      setTimeout(dropIfNoHost, 0);
    }
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

/** The host's subscription; when the current host unsubscribes, every waiting request resolves false. */
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
