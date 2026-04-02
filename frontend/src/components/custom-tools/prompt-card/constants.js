const LINE_ITEM_ENFORCE_TYPE = "line-item";
const TABLE = "table";
const AGENTIC_TABLE = "agentic_table";

const handleUpdateStatus = (isUpdate, promptId, value, setUpdateStatus) => {
  if (!isUpdate) {
    return;
  }
  setUpdateStatus({
    promptId: promptId,
    status: value,
  });
};

export { handleUpdateStatus, TABLE, AGENTIC_TABLE, LINE_ITEM_ENFORCE_TYPE };
