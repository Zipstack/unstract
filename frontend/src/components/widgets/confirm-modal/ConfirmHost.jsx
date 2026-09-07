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

import { getConfirmState, settleConfirm, subscribe } from "./confirmStore";

/**
 * Renders the app-wide confirm dialog. Mount once near the app root.
 *
 * Lives here rather than beside each caller so the dialog outlives the element
 * that opened it — see the note in confirmStore.js for why that matters.
 */
function ConfirmHost() {
  const state = React.useSyncExternalStore(
    subscribe,
    getConfirmState,
    () => null,
  );

  if (!state) {
    return null;
  }

  return (
    <AlertDialog
      open
      onOpenChange={(open) => {
        // Escape and outside-click must settle as Cancel, not leave the
        // promise pending.
        if (!open) {
          settleConfirm(false);
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state.title}</AlertDialogTitle>
          {state.content ? (
            <AlertDialogDescription>{state.content}</AlertDialogDescription>
          ) : null}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => settleConfirm(false)}>
            {state.cancelText}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={() => settleConfirm(true)}
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
  );
}

export { ConfirmHost };
