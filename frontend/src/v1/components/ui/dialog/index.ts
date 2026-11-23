// Public API; the gallery (`./dialog.gallery`) is imported directly, not from here.

export type { ConfirmError } from "./ConfirmDialog";
export { ConfirmHost, type ConfirmHostProps } from "./ConfirmHost";
export {
  type BlockedConfirm,
  type ConfirmOptions,
  confirm,
  type DestructiveConfirm,
  type StandardConfirm,
} from "./confirm";
export {
  Dialog,
  DialogBody,
  DialogCancel,
  type DialogCancelProps,
  DialogContent,
  type DialogContentProps,
  DialogFooter,
  DialogHeader,
  type DialogHeaderProps,
  type DialogProps,
  type DialogSize,
  DialogTrigger,
} from "./Dialog";
