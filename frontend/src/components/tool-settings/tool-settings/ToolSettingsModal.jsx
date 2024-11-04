import PropTypes from "prop-types";
import { useCallback } from "react";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";

function ToolSettingsModal({
  open,
  setOpen,
  editItem,
  isEdit,
  type,
  updateList,
}) {
  const handleAddNewItem = useCallback(
    (itemData) => {
      updateList(itemData, isEdit, editItem?.id);
      setOpen(false);
    },
    [isEdit, editItem?.id]
  );

  return (
    <AddSourceModal
      open={open}
      setOpen={setOpen}
      type={type}
      addNewItem={handleAddNewItem}
      editItemId={editItem?.id}
      setEditItemId={() => {}}
    />
  );
}

ToolSettingsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editItem: PropTypes.object,
  isEdit: PropTypes.bool.isRequired,
  handleAddItem: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  updateList: PropTypes.func.isRequired,
};

export default ToolSettingsModal;
