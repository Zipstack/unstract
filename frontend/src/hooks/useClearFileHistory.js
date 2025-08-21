import { useState } from "react";

import { workflowService } from "../components/workflows/workflow/workflow-service";
import { useAlertStore } from "../store/alert-store";
import { useExceptionHandler } from "./useExceptionHandler";

/**
 * Custom hook for clearing file history with loading state management
 * Prevents race conditions by tracking operation status
 * @return {Object} Object containing clearFileHistory function and isClearing state
 */
const useClearFileHistory = () => {
  const [isClearing, setIsClearing] = useState(false);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  // Get the workflow service instance at the top level of the hook
  const workflowServiceInstance = workflowService();

  /**
   * Clear file history for a workflow
   * @param {string} workflowId - The workflow ID
   * @param {string} successMessage - Custom success message
   * @return {Promise<boolean>} - Returns true if successful, false otherwise
   */
  const clearFileHistory = async (
    workflowId,
    successMessage = "File history cleared successfully"
  ) => {
    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content:
          "Cannot clear processed file history, workflow ID is undefined",
      });
      return false;
    }

    setIsClearing(true);

    try {
      const res = await workflowServiceInstance.clearFileMarkers(workflowId);
      const msg = res?.data || successMessage;
      setAlertDetails({
        type: "success",
        content: msg,
      });
      return true;
    } catch (err) {
      setAlertDetails(handleException(err, "Failed to clear file history"));
      return false;
    } finally {
      setIsClearing(false);
    }
  };

  return {
    clearFileHistory,
    isClearing,
  };
};

export default useClearFileHistory;
