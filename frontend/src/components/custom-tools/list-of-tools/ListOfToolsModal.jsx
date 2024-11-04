import PropTypes from "prop-types";
import { useCallback } from "react";
import { AddCustomToolFormModal } from "../add-custom-tool-form-modal/AddCustomToolFormModal";

function ListOfToolsModal({ open, setOpen, editItem, isEdit, handleAddItem }) {
  const handleAddNewTool = useCallback(
    (itemData) => handleAddItem(itemData, editItem?.tool_id, isEdit),
    [handleAddItem, isEdit, editItem?.tool_id]
  );

  return (
    <AddCustomToolFormModal
      open={open}
      setOpen={setOpen}
      editItem={editItem}
      isEdit={isEdit}
      handleAddNewTool={handleAddNewTool}
    />
  );
}

ListOfToolsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editItem: PropTypes.shape({
    tool_id: PropTypes.number,
    tool_name: PropTypes.string,
    description: PropTypes.string,
    icon: PropTypes.string,
  }),
  isEdit: PropTypes.bool.isRequired,
  handleAddItem: PropTypes.func.isRequired,
};

export default ListOfToolsModal;
