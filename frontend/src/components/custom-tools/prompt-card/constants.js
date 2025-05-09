const LINE_ITEM_ENFORCE_TYPE = "line-item";
const TABLE = "table";

const handleUpdateStatus = (isUpdate, promptId, value, setUpdateStatus) => {
  if (!isUpdate) {
    return;
  }
  setUpdateStatus({
    promptId: promptId,
    status: value,
  });
};

export { handleUpdateStatus, LINE_ITEM_ENFORCE_TYPE };
