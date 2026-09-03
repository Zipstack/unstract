import * as React from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

/**
 * Promise-returning confirmation dialog (P2-01).
 *
 * Replaces antd's imperative `Modal.confirm({ onOk })` style with
 * `if (await confirm({...})) { ... }`, so a call-site reads top-to-bottom
 * instead of splitting across callbacks.
 *
 * This is OSS-owned on purpose (D9 / §5.0): the cloud plugins have 3
 * `Modal.confirm` sites that must import this rather than reimplement it, and
 * `Popconfirm` (8 OSS sites) is routed through it too.
 *
 * Usage:
 *   const { confirm, confirmDialog } = useConfirm();
 *   ...
 *   if (await confirm({ title: "Delete?", okText: "Delete", danger: true })) {
 *     doDelete();
 *   }
 *   return <>{confirmDialog}...</>;
 */
export function useConfirm() {
  const [state, setState] = React.useState(null);
  // Held in a ref so resolving does not depend on a re-render.
  const resolver = React.useRef(null);

  const confirm = React.useCallback((options = {}) => {
    return new Promise((resolve) => {
      resolver.current = resolve;
      setState({
        title: options.title ?? "Are you sure?",
        description: options.description ?? options.content ?? "",
        okText: options.okText ?? "OK",
        cancelText: options.cancelText ?? "Cancel",
        danger: options.danger ?? options.okType === "danger",
      });
    });
  }, []);

  const settle = React.useCallback((result) => {
    setState(null);
    resolver.current?.(result);
    resolver.current = null;
  }, []);

  const confirmDialog = state ? (
    <AlertDialog
      open
      onOpenChange={(open) => {
        // Covers Escape and outside-click, which must resolve false rather
        // than leaving the promise pending forever.
        if (!open) {
          settle(false);
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state.title}</AlertDialogTitle>
          {state.description ? (
            <AlertDialogDescription>{state.description}</AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => settle(false)}>
            {state.cancelText}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={() => settle(true)}
            className={
              state.danger
                ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                : undefined
            }
          >
            {state.okText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  ) : null;

  return { confirm, confirmDialog };
}
