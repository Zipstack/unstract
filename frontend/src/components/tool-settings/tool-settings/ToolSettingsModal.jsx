import PropTypes from "prop-types";
import { useCallback } from "react";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";

function ToolSettingsModal({
  open,
  setOpen,
  editItem,
  isEdit,
  handleAddItem,
  type,
}) {
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const handleAddNewItem = useCallback(
    (itemData) => {
      handleAddItem(itemData, isEdit, editItem?.id)
        .then(() => {
          setOpen(false);
        })
        .catch((err) => {
          setAlertDetails(handleException(err, "Failed to add/edit adapter"));
        });
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
};

export default ToolSettingsModal;
