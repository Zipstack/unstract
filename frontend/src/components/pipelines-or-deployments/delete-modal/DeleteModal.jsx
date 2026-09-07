import PropTypes from "prop-types";
import { Modal } from "@/components/ui/shims/antd-overlays";

const DeleteModal = ({ open, setOpen, deleteRecord }) => {
  return (
    <Modal
      title="Are you sure you want to delete this?"
      centered
      open={open}
      onOk={deleteRecord}
      onCancel={() => setOpen(false)}
      okText="Delete"
      width={500}
    ></Modal>
  );
};

DeleteModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  deleteRecord: PropTypes.func.isRequired,
};

export { DeleteModal };
