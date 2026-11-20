import { useCallback, useRef } from "react";

export type CloseGuard = Readonly<{
  /** While true, a request to close is ignored. */
  busy?: boolean;
  /** The dirty guard: asked before every close; false keeps the dialog open. */
  beforeClose?: () => boolean | Promise<boolean>;
  onOpenChange: (open: boolean) => void;
}>;

async function closeIfAllowed(
  guard: () => boolean | Promise<boolean>,
  close: () => void,
): Promise<void> {
  if (await guard()) {
    close();
  }
}

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
  return useCallback(
    (open: boolean) => {
      if (open) {
        onOpenChange(true);
        return;
      }
      if (busy || asking.current) {
        return;
      }
      if (!beforeClose) {
        onOpenChange(false);
        return;
      }
      asking.current = true;
      const close = () => onOpenChange(false);
      void closeIfAllowed(beforeClose, close).finally(() => {
        asking.current = false;
      });
    },
    [beforeClose, busy, onOpenChange],
  );
}
