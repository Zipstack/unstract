import { Modal, Space } from "antd";
import PropTypes from "prop-types";

function ConfirmModal({
  children,
  handleConfirm,
  title,
  content,
  okText,
  cancelText,
}) {
  const [modal, contextHolder] = Modal.useModal();

  const handleConfirmModal = () => {
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
};

export { ConfirmModal };
