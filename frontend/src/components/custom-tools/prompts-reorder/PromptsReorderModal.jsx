import { Modal } from "antd";
import PropTypes from "prop-types";

import { PromptsReorder } from "./PromptsReorder";

function PromptsReorderModal({ open, setOpen, updateReorderedStatus }) {
  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      title="Reorder Prompts"
      footer={null}
      maskClosable={false}
      centered
    >
      <PromptsReorder
        isOpen={open}
        updateReorderedStatus={updateReorderedStatus}
      />
    </Modal>
  );
}

PromptsReorderModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  updateReorderedStatus: PropTypes.func.isRequired,
};

export { PromptsReorderModal };
