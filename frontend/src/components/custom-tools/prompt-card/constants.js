const TABLE_ENFORCE_TYPE = "table";
const RECORD_ENFORCE_TYPE = "record";

const handleUpdateStatus = (isUpdate, promptId, value, setUpdateStatus) => {
  if (!isUpdate) {
    return;
  }
  setUpdateStatus({
    promptId: promptId,
    status: value,
  });
};

export { TABLE_ENFORCE_TYPE, handleUpdateStatus, RECORD_ENFORCE_TYPE };
