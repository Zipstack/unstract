import { Modal } from "antd";
import PropTypes from "prop-types";

import { ManageLlmProfiles } from "../manage-llm-profiles/ManageLlmProfiles";

function ManageLlmProfilesModal({
  open,
  setOpen,
  setOpenLlm,
  setEditLlmProfileId,
  setModalTitle,
}) {
  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      width={1000}
      maskClosable={false}
    >
      <ManageLlmProfiles
        setOpen={setOpen}
        setOpenLlm={setOpenLlm}
        setEditLlmProfileId={setEditLlmProfileId}
        setModalTitle={setModalTitle}
      />
    </Modal>
  );
}

ManageLlmProfilesModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  setOpenLlm: PropTypes.func.isRequired,
  setEditLlmProfileId: PropTypes.func.isRequired,
  setModalTitle: PropTypes.func.isRequired,
};

export { ManageLlmProfilesModal };
