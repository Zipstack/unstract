import { getPortalContainer } from "@v1/lib/portal";
import {
  type JSX,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { ConfirmDialog } from "./ConfirmDialog";
import {
  type ConfirmRequest,
  currentConfirm,
  setConfirmRunning,
  settleConfirm,
  subscribeConfirm,
} from "./confirm";

/** Answers this soon after a request shows are ignored: the second click of a double click. */
export const ANSWER_GUARD_MS = 400;

// A queued request reuses the open dialog, so focus moves to its default button.
function useFocusOnSwap(id: number | null): void {
  const shown = useRef<number | null>(null);
  useEffect(() => {
    if (shown.current !== null && id !== null && id !== shown.current) {
      getPortalContainer()
        .querySelector<HTMLElement>(
          "[data-slot=confirm-dialog] [data-autofocus]",
        )
        ?.focus();
    }
    shown.current = id;
  }, [id]);
}

/** True once the request on screen has shown for `ANSWER_GUARD_MS`. */
function useAnswerable(id: number | null): () => boolean {
  const shown = useRef({ id, at: 0 });
  useLayoutEffect(() => {
    shown.current = { id, at: Date.now() };
  }, [id]);
  return () => Date.now() - shown.current.at >= ANSWER_GUARD_MS;
}

/** Runs the request's action while busy; a failure is logged and the dialog stays open. */
function useConfirmAction(): [
  number | null,
  (request: ConfirmRequest) => void,
] {
  const [busyId, setBusyId] = useState<number | null>(null);
  const run = useCallback(async ({ id, options }: ConfirmRequest) => {
    const action = options.tone === "blocked" ? undefined : options.action;
    if (!action) {
      settleConfirm(id, true);
      return;
    }
    setBusyId(id);
    setConfirmRunning(true);
    try {
      await action();
      settleConfirm(id, true);
    } catch (error) {
      console.error("[v1 confirm] action failed: %s", options.title, error);
    } finally {
      setConfirmRunning(false);
      setBusyId(null);
    }
  }, []);
  return [busyId, (request) => void run(request)];
}

function followLink({ id, options }: ConfirmRequest): void {
  settleConfirm(id, false);
  if (options.tone === "blocked") {
    options.link?.onSelect();
  }
}

/** Shows the `confirm()` queue, one request at a time. Mounted beside each v1 page. */
export function ConfirmHost(): JSX.Element {
  const request = useSyncExternalStore(
    subscribeConfirm,
    currentConfirm,
    currentConfirm,
  );
  const id = request?.id ?? null;
  const [busyId, run] = useConfirmAction();
  const answerable = useAnswerable(id);
  useFocusOnSwap(id);
  // Not straight after a request shows: that is the second click of a double click.
  const answer = (then: (request: ConfirmRequest) => void) => () => {
    if (request && answerable()) {
      then(request);
    }
  };
  return (
    <ConfirmDialog
      options={request?.options ?? null}
      busy={id !== null && busyId === id}
      onConfirm={answer(run)}
      onDismiss={answer(({ id: headId }) => settleConfirm(headId, false))}
      onLink={answer(followLink)}
    />
  );
}
