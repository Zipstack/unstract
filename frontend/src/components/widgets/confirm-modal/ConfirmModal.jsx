import PropTypes from "prop-types";
import { Space } from "@/components/ui/shims/antd-layout";
import { Modal } from "@/components/ui/shims/antd-overlays";

function ConfirmModal({
  children,
  handleConfirm,
  title,
  content,
  okText,
  cancelText,
  isDisabled = false,
}) {
  const [modal, contextHolder] = Modal.useModal();

  const handleConfirmModal = () => {
    if (isDisabled) {
      handleConfirm();
      return;
    }

    modal.confirm({
      title: title || "Are you sure?",
      content: content || "",
      okText: okText || "Confirm",
      cancelText: cancelText || "Cancel",
      onOk: handleConfirm,
      centered: true,
    });
  };

  return (
    <>
      <Space onClick={handleConfirmModal}>{children}</Space>
      {contextHolder}
    </>
  );
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
