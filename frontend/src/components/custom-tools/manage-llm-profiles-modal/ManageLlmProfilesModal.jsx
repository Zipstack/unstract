import { Modal } from "antd";
import PropTypes from "prop-types";
import { ManageLlmProfiles } from "../manage-llm-profiles/ManageLlmProfiles";

function ManageLlmProfilesModal({
  open,
  setOpen,
  setOpenLlm,
  setEditLlmProfileId,
}) {
  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      width={800}
      maskClosable={false}
    >
      <ManageLlmProfiles
        setOpen={setOpen}
        setOpenLlm={setOpenLlm}
        setEditLlmProfileId={setEditLlmProfileId}
      />
    </Modal>
  );
}

ManageLlmProfilesModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  setOpenLlm: PropTypes.func.isRequired,
  setEditLlmProfileId: PropTypes.func.isRequired,
};

export { ManageLlmProfilesModal };
