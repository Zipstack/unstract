const LINE_ITEM_ENFORCE_TYPE = "line-item";
const TABLE = "table";

/**
 * A backend-produced highlight payload is a non-empty array of coordinate
 * arrays. Shared by PromptCard (highlight state gate) and DisplayPromptResult
 * (clickable-render gate) so the two gates cannot drift apart — a looser gate
 * on one side would set highlight state that the other side never renders.
 */
const hasHighlightData = (highlightData) =>
  Array.isArray(highlightData) && highlightData.length > 0;

const handleUpdateStatus = (isUpdate, promptId, value, setUpdateStatus) => {
  if (!isUpdate) {
    return;
  }
  setUpdateStatus({
    promptId: promptId,
    status: value,
  });
};

export { handleUpdateStatus, hasHighlightData, LINE_ITEM_ENFORCE_TYPE, TABLE };
