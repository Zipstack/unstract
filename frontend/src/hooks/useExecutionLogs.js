import { useRef, useState } from "react";

import { fetchExecutionLogs } from "../components/pipelines-or-deployments/log-modal/fetchExecutionLogs";

/**
 * Shared hook for execution logs modal state and fetching.
 * Tracks the selected item via ref so pagination works after the initial fetch.
 *
 * @param {Object} options
 * @param {Function} options.axiosPrivate
 * @param {Function} options.handleException
 * @param {Object} options.sessionDetails
 * @param {Function} options.setAlertDetails
 * @return {Object} Logs modal state and handlers
 */
function useExecutionLogs({
  axiosPrivate,
  handleException,
  sessionDetails,
  setAlertDetails,
}) {
  const [openLogsModal, setOpenLogsModal] = useState(false);
  const [executionLogs, setExecutionLogs] = useState([]);
  const [executionLogsTotalCount, setExecutionLogsTotalCount] = useState(0);
  const [isFetchingLogs, setIsFetchingLogs] = useState(false);

  const logsItemRef = useRef(null);

  const handleFetchLogs = (page, pageSize) => {
    fetchExecutionLogs(
      axiosPrivate,
      handleException,
      sessionDetails,
      logsItemRef.current,
      setExecutionLogs,
      setExecutionLogsTotalCount,
      setAlertDetails,
      page,
      pageSize,
      setIsFetchingLogs,
    );
  };

  /**
   * Open the logs modal for a given item and trigger the initial fetch.
   * @param {Object} item - the pipeline/deployment to view logs for
   * @param {Function} setSelectedItem - parent's selected-item setter
   */
  const handleViewLogs = (item, setSelectedItem) => {
    setSelectedItem(item);
    logsItemRef.current = item;
    setOpenLogsModal(true);
    fetchExecutionLogs(
      axiosPrivate,
      handleException,
      sessionDetails,
      item,
      setExecutionLogs,
      setExecutionLogsTotalCount,
      setAlertDetails,
      1,
      10,
      setIsFetchingLogs,
    );
  };

  return {
    openLogsModal,
    setOpenLogsModal,
    executionLogs,
    executionLogsTotalCount,
    isFetchingLogs,
    handleFetchLogs,
    handleViewLogs,
  };
}

export { useExecutionLogs };
