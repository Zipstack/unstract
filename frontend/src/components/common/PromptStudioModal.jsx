import { Button, Modal } from "antd";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";

import { useSessionStore } from "../../store/session-store";
import "./PromptStudioModal.css";

export function PromptStudioModal({ onClose, showModal }) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();

  const handleClose = () => {
    if (onClose) onClose();
  };

  const handleCreateClick = () => {
    navigate(`/${sessionDetails?.orgName}/tools`);
    handleClose();
  };

  return (
    <Modal
      title="Create Prompt Studio"
      open={showModal}
      onCancel={handleClose}
      footer={null}
      centered
      width={500}
      maskClosable={false}
      className="prompt-studio-modal"
      closeIcon={<span>×</span>}
    >
      <div className="prompt-studio-description">
        You first need to create and export a Prompt Studio project or export an
        existing sample Prompt Studio project before you can create a workflow.
      </div>
      <div className="prompt-studio-buttons">
        <Button
          type="link"
          onClick={handleCreateClick}
          className="prompt-studio-guide-btn"
        >
          + Create Prompt Studio
        </Button>
        <Button
          type="link"
          href="https://docs.unstract.com/unstract/unstract_platform/quick_start/"
          target="_blank"
          className="prompt-studio-guide-btn"
        >
          Quick Start Guide
        </Button>
        <Button
          type="text"
          onClick={handleClose}
          className="prompt-studio-cancel-btn"
        >
          Cancel
        </Button>
      </div>
    </Modal>
  );
}

PromptStudioModal.propTypes = {
  onClose: PropTypes.func,
  showModal: PropTypes.bool,
};

PromptStudioModal.defaultProps = {
  onClose: null,
  showModal: false,
};
