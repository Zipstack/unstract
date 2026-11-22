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

const FAILED_MESSAGE = "Something went wrong. Try again.";

type Failure = Readonly<{ id: number; message: string }>;

/** Runs request `id`'s action marked as running; resolves to what it threw, or null on success. */
async function attempt(
  { id, options }: ConfirmRequest,
  action: () => Promise<void>,
): Promise<{ error: unknown } | null> {
  setConfirmRunning(id, true);
  try {
    await action();
    settleConfirm(id, true);
    return null;
  } catch (error) {
    console.error("[v1 confirm] action failed: %s", options.title, error);
    return { error };
  } finally {
    setConfirmRunning(id, false);
  }
}

/** Runs the request's action while busy; a failure is logged and shown, and the dialog stays open. */
function useConfirmAction(describeError: (error: unknown) => string) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const run = useCallback(
    async (request: ConfirmRequest) => {
      const { id, options } = request;
      const action = options.tone === "blocked" ? undefined : options.action;
      if (!action) {
        settleConfirm(id, true);
        return;
      }
      setFailure(null);
      setBusyId(id);
      const failed = await attempt(request, action);
      setBusyId(null);
      if (failed) {
        setFailure({ id, message: describeError(failed.error) });
      }
    },
    [describeError],
  );
  return {
    busyId,
    failure,
    run: (request: ConfirmRequest) => void run(request),
  };
}

function followLink({ id, options }: ConfirmRequest): void {
  settleConfirm(id, false);
  if (options.tone === "blocked") {
    options.link?.onSelect();
  }
}

export type ConfirmHostProps = Readonly<{
  /** Words a failed action's error for the dialog; the app passes the API error's message. */
  describeError?: (error: unknown) => string;
}>;

const describeAnyError = () => FAILED_MESSAGE;

/** Shows the `confirm()` queue, one request at a time. Mounted beside each v1 page. */
export function ConfirmHost({
  describeError = describeAnyError,
}: ConfirmHostProps): JSX.Element {
  const request = useSyncExternalStore(
    subscribeConfirm,
    currentConfirm,
    currentConfirm,
  );
  const id = request?.id ?? null;
  const { busyId, failure, run } = useConfirmAction(describeError);
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
      error={failure?.id === id ? failure.message : undefined}
      onConfirm={answer(run)}
      onDismiss={answer(({ id: headId }) => settleConfirm(headId, false))}
      onLink={answer(followLink)}
    />
  );
}
