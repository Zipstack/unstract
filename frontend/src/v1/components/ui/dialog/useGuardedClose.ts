import { useCallback, useRef } from "react";

export type CloseGuard = Readonly<{
  /** While true, a request to close is ignored. */
  busy?: boolean;
  /** The dirty guard: asked before every close; false keeps the dialog open. */
  beforeClose?: () => boolean | Promise<boolean>;
  onOpenChange: (open: boolean) => void;
}>;

/**
 * Wraps `onOpenChange` so every close path first passes `busy` and
 * `beforeClose`; a request while the guard is asking is ignored.
 */
export function useGuardedClose({
  busy = false,
  beforeClose,
  onOpenChange,
}: CloseGuard): (open: boolean) => void {
  const asking = useRef(false);

  const ask = useCallback(
    async (guard: () => boolean | Promise<boolean>) => {
      asking.current = true;
      try {
        if (await guard()) {
          onOpenChange(false);
        }
      } finally {
        asking.current = false;
      }
    },
    [onOpenChange],
  );

  return useCallback(
    (open: boolean) => {
      if (open) {
        onOpenChange(true);
        return;
      }
      if (busy || asking.current) {
        return;
      }
      if (beforeClose) {
        void ask(beforeClose);
        return;
      }
      onOpenChange(false);
    },
    [ask, beforeClose, busy, onOpenChange],
  );
}
