import PropTypes from "prop-types";
import { Space } from "@/components/ui/shims/antd-layout";

import { openConfirm } from "./confirmStore";

/**
 * Wraps its children in a click target that asks for confirmation first.
 *
 * The dialog opens through the module-level store rather than a local
 * `Modal.useModal()` holder. Several call-sites — Delete in a prompt card's
 * kebab menu, most notably — sit inside a Radix DropdownMenu, which unmounts
 * its content the moment an item is clicked. A holder rendered as a sibling of
 * `children` died in that same tick, so the dialog never appeared and Delete
 * silently did nothing at all. See confirmStore.js.
 */
function ConfirmModal({
  children,
  handleConfirm,
  title,
  content,
  okText,
  cancelText,
  isDisabled = false,
}) {
  const handleConfirmModal = () => {
    if (isDisabled) {
      handleConfirm();
      return;
    }

    openConfirm({
      title: title || "Are you sure?",
      content: content || "",
      okText: okText || "Confirm",
      cancelText: cancelText || "Cancel",
      onOk: handleConfirm,
    });
  };

  return <Space onClick={handleConfirmModal}>{children}</Space>;
}

ConfirmModal.propTypes = {
  children: PropTypes.any.isRequired,
  handleConfirm: PropTypes.func.isRequired,
  title: PropTypes.string,
  content: PropTypes.string,
  okText: PropTypes.string,
  cancelText: PropTypes.string,
  isDisabled: PropTypes.bool,
};

export { ConfirmModal };
