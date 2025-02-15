import { useEffect, useState, useCallback } from "react";
import PropTypes from "prop-types";
import { CustomButton } from "../widgets/custom-button/CustomButton";
import { ToolNavBar } from "../navigations/tool-nav-bar/ToolNavBar";
import { ViewTools } from "../custom-tools/view-tools/ViewTools";
import "./ViewProjects.css";

function ListView({
  title,
  useListManagerHook,
  CustomModalComponent,
  customButtonText,
  customButtonIcon,
  onCustomButtonClick,
  handleEditItem,
  handleDeleteItem,
  itemProps,
  setPostHogCustomEvent,
  newButtonEventName,
  type,
}) {
  const {
    list,
    filteredList,
    loading,
    fetchList,
    handleSearch,
    handleAddItem,
    handleDeleteItem: deleteItem,
    updateList,
  } = useListManagerHook;

  const [openModal, setOpenModal] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [isEdit, setIsEdit] = useState(false);

  useEffect(() => {
    fetchList();
  }, [title]);

  const handleCustomButtonClick = useCallback(() => {
    setEditingItem(null);
    setIsEdit(false);
    setOpenModal(true);
    if (onCustomButtonClick) onCustomButtonClick();
    try {
      setPostHogCustomEvent?.(newButtonEventName, {
        info: `Clicked on '${customButtonText}' button`,
      });
    } catch (err) {
      // Ignore error
    }
  }, [onCustomButtonClick, newButtonEventName, customButtonText]);

  const CustomButtons = useCallback(
    () => (
      <CustomButton
        type="primary"
        icon={customButtonIcon}
        onClick={handleCustomButtonClick}
      >
        {customButtonText}
      </CustomButton>
    ),
    [customButtonIcon, handleCustomButtonClick, customButtonText]
  );

  const handleEdit = useCallback(
    (_event, item) => {
      setEditingItem(item);
      setIsEdit(true);
      setOpenModal(true);
      if (handleEditItem) handleEditItem(item);
    },
    [handleEditItem]
  );

  const handleDelete = useCallback(
    (_event, item) => {
      deleteItem(item?.[itemProps?.idProp]);
      if (handleDeleteItem) handleDeleteItem(item);
    },
    [deleteItem, handleDeleteItem, itemProps?.idProp]
  );

  return (
    <>
      <ToolNavBar
        title={title}
        enableSearch
        onSearch={handleSearch}
        searchList={list}
        setSearchList={filteredList}
        CustomButtons={CustomButtons}
      />
      <div className="list-of-tools-layout">
        <div className="list-of-tools-island">
          <div className="list-of-tools-body">
            <ViewTools
              isLoading={loading}
              isEmpty={!filteredList?.length}
              listOfTools={filteredList}
              setOpenAddTool={setOpenModal}
              handleEdit={handleEdit}
              handleDelete={handleDelete}
              {...itemProps}
            />
          </div>
        </div>
      </div>
      {openModal && CustomModalComponent && (
        <CustomModalComponent
          open={openModal}
          setOpen={setOpenModal}
          editItem={editingItem}
          isEdit={isEdit}
          handleAddItem={handleAddItem}
          updateList={updateList}
          type={type}
        />
      )}
    </>
  );
}

ListView.propTypes = {
  title: PropTypes.string.isRequired,
  useListManagerHook: PropTypes.shape({
    list: PropTypes.array.isRequired,
    filteredList: PropTypes.array.isRequired,
    loading: PropTypes.bool.isRequired,
    fetchList: PropTypes.func.isRequired,
    handleSearch: PropTypes.func.isRequired,
    handleAddItem: PropTypes.func.isRequired,
    handleDeleteItem: PropTypes.func.isRequired,
    updateList: PropTypes.func.isRequired,
  }).isRequired,
  CustomModalComponent: PropTypes.oneOfType([
    PropTypes.func,
    PropTypes.elementType,
  ]),
  customButtonText: PropTypes.string.isRequired,
  customButtonIcon: PropTypes.element,
  onCustomButtonClick: PropTypes.func,
  handleEditItem: PropTypes.func,
  handleDeleteItem: PropTypes.func,
  itemProps: PropTypes.shape({
    titleProp: PropTypes.string.isRequired,
    descriptionProp: PropTypes.string,
    iconProp: PropTypes.string,
    idProp: PropTypes.string.isRequired,
    type: PropTypes.string.isRequired,
  }).isRequired,
  setPostHogCustomEvent: PropTypes.func,
  newButtonEventName: PropTypes.string,
  type: PropTypes.string,
};

export { ListView };
