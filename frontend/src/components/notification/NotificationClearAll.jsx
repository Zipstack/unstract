import { X } from "lucide-react";
import { useSonner } from "sonner";
import { Button } from "@/components/ui/button";
import { dismissAppToast } from "@/hooks/useAppToast";

/**
 * "Clear all" affordance for the toast stack.
 *
 * Error alerts are sticky (`duration: 0`, see `useExceptionHandler`) so the
 * user can read and copy the Request ID. That is deliberate, but it means a
 * repeated failure leaves a pile of toasts that each need their own close
 * button. This clears the pile in one click.
 *
 * Sits in the band that `<Toaster offset>` reserves above the stack in
 * App.jsx — the two values are a pair, so changing one means changing the
 * other. Rendered only when there is more than one toast, since a single
 * toast's own close button is already a one-click dismiss.
 */
function NotificationClearAll() {
  const { toasts } = useSonner();

  if (toasts.length < 2) {
    return null;
  }

  return (
    <div className="notification-clear-all">
      <Button
        variant="secondary"
        size="xs"
        onClick={() => dismissAppToast()}
        aria-label={`Clear all ${toasts.length} notifications`}
      >
        <X />
        Clear all ({toasts.length})
      </Button>
    </div>
  );
}

export { NotificationClearAll };
