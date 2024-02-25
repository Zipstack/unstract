import { Modal } from "antd";
import PropTypes from "prop-types";

import { Configuration } from "../configuration/Configuration";

function ConfigurationModal({ isOpen, setOpen }) {
  return (
    <Modal
      open={isOpen}
      onCancel={() => setOpen(false)}
      footer={false}
      closable={true}
      maskClosable={false}
    >
      <Configuration setOpen={setOpen} />
    </Modal>
  );
}

ConfigurationModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};

export { ConfigurationModal };
