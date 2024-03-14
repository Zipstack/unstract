import { Modal } from "antd";
import PropTypes from "prop-types";

import { CustomSynonyms } from "../custom-synonyms/CustomSynonyms";

function CustomSynonymsModal({ open, setOpen }) {
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
      <CustomSynonyms setOpen={setOpen} />
    </Modal>
  );
}

CustomSynonymsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};

export { CustomSynonymsModal };
