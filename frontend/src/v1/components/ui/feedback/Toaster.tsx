import { cn } from "@v1/lib/cn";
import { type NotifyInput, type NotifyKind, setNotifier } from "@v1/lib/notify";
import { getPortalContainer } from "@v1/lib/portal";
import { X } from "lucide-react";
import { Toast as RadixToast } from "radix-ui";
import {
  type JSX,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { KIND_ICON, KIND_TEXT } from "./kinds";

/** How long a toast stays when it is not persistent. */
export const TOAST_DURATION_MS = 6000;

/** Toasts shown at once; older ones close first. */
export const MAX_TOASTS = 3;

/*
 * `id` is the caller's handle (replace and dismiss go through it); `rev` is
 * one `show()` call. Keying and removing by `rev` means a replacement mounts a
 * fresh Radix toast (its own timer, `persistent` and announcement), and an
 * action that re-notifies its own id is not removed by its own close.
 */
type Entry = NotifyInput & Readonly<{ id: string; rev: number }>;

export type ToasterProps = Readonly<{
  /** Overrides the default timeout (tests, or a page that needs longer). */
  duration?: number;
  /** Where the viewport renders; the v1 portal container by default. */
  container?: HTMLElement;
}>;

let sequence = 0;
const nextId = () => {
  sequence += 1;
  return `toast-${sequence}`;
};
let revision = 0;
const nextRev = () => {
  revision += 1;
  return revision;
};

/*
 * Keeps at most MAX_TOASTS. The newest always stays; older timed toasts go
 * first, and a persistent one goes only when every other toast is persistent
 * too (the cap still wins, so the stack cannot grow without bound).
 */
function capped(entries: readonly Entry[]): readonly Entry[] {
  const kept = [...entries];
  while (kept.length > MAX_TOASTS) {
    const older = kept.slice(0, -1);
    const timed = older.findIndex((e) => !e.persistent);
    kept.splice(timed === -1 ? 0 : timed, 1);
  }
  return kept;
}

/**
 * The single toast region of v1. Mount it once, inside the v1 root; it
 * registers itself as the notifier, so `notify()` and `toast.*` reach it.
 * Toasts stack bottom-right, pause while hovered or focused, and F8 moves
 * focus to them so an action is reachable by keyboard.
 */
export function Toaster({
  duration = TOAST_DURATION_MS,
  container,
}: ToasterProps): JSX.Element {
  const [entries, setEntries] = useState<readonly Entry[]>([]);
  const [target, setTarget] = useState<HTMLElement | null>(container ?? null);
  // Bumped when the last toast goes, so the provider remounts: Radix leaves its
  // hover pause set when the viewport empties under the pointer, and the next
  // toast would otherwise never time out.
  const [generation, setGeneration] = useState(0);
  const current = useRef<readonly Entry[]>([]);
  const viewportRef = useRef<HTMLOListElement>(null);
  const refocus = useRef(false);

  // The remount replaces the viewport; keep focus on it rather than <body>.
  // biome-ignore lint/correctness/useExhaustiveDependencies: runs per remount.
  useLayoutEffect(() => {
    if (refocus.current) {
      refocus.current = false;
      viewportRef.current?.focus();
    }
  }, [generation]);

  // Every change goes through here, synchronously, so several calls in one
  // tick see each other's result.
  const commit = useCallback((next: readonly Entry[]) => {
    const prev = current.current;
    const kept = new Set(next.map((e) => e.rev));
    // Removing a focused toast would drop focus to <body>; Radix only moves it
    // for closes it runs itself.
    const focused =
      document.activeElement?.closest<HTMLElement>("[data-slot=toast]");
    if (focused && !kept.has(Number(focused.dataset.rev))) {
      viewportRef.current?.focus();
      // Only a remount replaces the viewport; a stale flag would steal focus
      // later, when some other change empties the list.
      refocus.current = next.length === 0;
    }
    current.current = next;
    setEntries(next);
    if (next.length === 0 && prev.length > 0) {
      setGeneration((g) => g + 1);
    }
  }, []);

  const removeRev = useCallback(
    (rev: number) => commit(current.current.filter((e) => e.rev !== rev)),
    [commit],
  );

  useLayoutEffect(() => {
    setTarget(container ?? getPortalContainer());
    return setNotifier({
      show: (input) => {
        const id = input.id ?? nextId();
        const others = current.current.filter((e) => e.id !== id);
        commit(capped([...others, { ...input, id, rev: nextRev() }]));
        return id;
      },
      dismiss: (id) => commit(current.current.filter((e) => e.id !== id)),
    });
  }, [commit, container]);

  const viewport = (
    <RadixToast.Viewport
      ref={viewportRef}
      label="Notifications ({hotkey})"
      className="ui:fixed ui:right-0 ui:bottom-0 ui:box-border ui:z-50 ui:m-0 ui:flex ui:max-h-screen ui:w-full ui:max-w-108 ui:list-none ui:flex-col ui:gap-3 ui:p-4 ui:outline-none"
    />
  );

  return (
    <RadixToast.Provider
      key={generation}
      duration={duration}
      swipeDirection="right"
      // No swipe styles exist in the design, so a drag would close a toast
      // that never visibly moved; the threshold switches the gesture off.
      swipeThreshold={Number.POSITIVE_INFINITY}
      label="Notification"
    >
      {entries.map((entry) => (
        <ToastItem
          key={entry.rev}
          entry={entry}
          onClose={() => removeRev(entry.rev)}
        />
      ))}
      {target ? createPortal(viewport, target) : null}
    </RadixToast.Provider>
  );
}

type ToastItemProps = Readonly<{ entry: Entry; onClose: () => void }>;

function ToastItem({ entry, onClose }: ToastItemProps): JSX.Element {
  const Icon = KIND_ICON[entry.kind];

  return (
    <RadixToast.Root
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      duration={entry.persistent ? Number.POSITIVE_INFINITY : undefined}
      type={assertive(entry.kind) ? "foreground" : "background"}
      data-slot="toast"
      data-kind={entry.kind}
      data-rev={entry.rev}
      className={cn(
        "ui:box-border ui:flex ui:w-full ui:items-start ui:gap-3 ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:py-3.5 ui:pr-3.5 ui:pl-4 ui:text-popover-foreground ui:shadow-md ui:focus-visible:focus-ring",
      )}
    >
      <Icon
        aria-hidden
        className={cn(
          "ui:mt-px ui:size-4.5 ui:shrink-0",
          KIND_TEXT[entry.kind],
        )}
      />
      <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-1">
        <RadixToast.Title className="ui:text-body ui:font-semibold ui:text-foreground">
          {entry.title}
        </RadixToast.Title>
        {entry.description ? (
          <RadixToast.Description className="ui:text-body-small ui:text-muted-foreground">
            {entry.description}
          </RadixToast.Description>
        ) : null}
        {entry.requestId ? (
          // Radix makes the toast unselectable for swiping; the id must copy.
          <p className="ui:m-0 ui:select-text ui:text-caption ui:text-muted-foreground">
            Request ID: {entry.requestId}
          </p>
        ) : null}
        {entry.action ? (
          <RadixToast.Action
            altText={entry.action.label}
            onClick={() => entry.action?.onSelect()}
            className="ui:mt-1 ui:cursor-pointer ui:self-start ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-body-small ui:font-medium ui:text-primary ui:hover:underline ui:focus-visible:focus-ring"
          >
            {entry.action.label}
          </RadixToast.Action>
        ) : null}
      </div>
      <RadixToast.Close
        aria-label="Dismiss notification"
        className="ui:inline-flex ui:size-6 ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:hover:bg-accent ui:hover:text-foreground ui:focus-visible:focus-ring"
      >
        <X aria-hidden className="ui:size-3.5" />
      </RadixToast.Close>
    </RadixToast.Root>
  );
}

/** Errors interrupt; everything else waits for a pause. */
function assertive(kind: NotifyKind): boolean {
  return kind === "error";
}
