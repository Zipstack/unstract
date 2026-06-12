import { Modal } from "antd";
import PropTypes from "prop-types";

const DeleteModal = ({
  open,
  setOpen,
  deleteRecord,
  entityType,
  entityName,
}) => {
  const title = entityName
    ? `Are you sure you want to delete the ${entityType || "item"} '${entityName}'?`
    : "Are you sure you want to delete this?";
  return (
    <Modal
      title={title}
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
  entityType: PropTypes.string,
  entityName: PropTypes.string,
};

export { DeleteModal };
