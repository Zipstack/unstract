import { getPortalContainer } from "@v1/lib/portal";
import {
  type JSX,
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { ConfirmDialog } from "./ConfirmDialog";
import {
  type ConfirmRequest,
  currentConfirm,
  settleConfirm,
  subscribeConfirm,
} from "./confirm";

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

/** Runs the request's action while busy; a failure is logged and the dialog stays open. */
function useConfirmAction(): [
  number | null,
  (request: ConfirmRequest) => void,
] {
  const [busyId, setBusyId] = useState<number | null>(null);
  const run = useCallback(async (request: ConfirmRequest) => {
    const { options } = request;
    const action = options.tone === "blocked" ? undefined : options.action;
    if (!action) {
      settleConfirm(request.id, true);
      return;
    }
    setBusyId(request.id);
    try {
      await action();
      settleConfirm(request.id, true);
    } catch (error) {
      console.error("[v1 confirm] action failed: %s", options.title, error);
    } finally {
      setBusyId(null);
    }
  }, []);
  return [busyId, (request) => void run(request)];
}

/** Shows the `confirm()` queue, one request at a time. Mount it once, in V1App. */
export function ConfirmHost(): JSX.Element {
  const request = useSyncExternalStore(
    subscribeConfirm,
    currentConfirm,
    currentConfirm,
  );
  const id = request?.id ?? null;
  const [busyId, run] = useConfirmAction();
  useFocusOnSwap(id);
  return (
    <ConfirmDialog
      options={request?.options ?? null}
      busy={id !== null && busyId === id}
      onConfirm={() => request && run(request)}
      onDismiss={() => id !== null && settleConfirm(id, false)}
    />
  );
}
