const fetchExecutionLogs = (
  axiosPrivate,
  handleException,
  sessionDetails,
  selectedRow,
  setExecutionLogs,
  setExecutionLogsTotalCount,
  setAlertDetails,
  page = 1,
  pageSize = 10,
) => {
  const requestOptions = {
    method: "GET",
    url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/${selectedRow.id}/executions/`,
    headers: {
      "X-CSRFToken": sessionDetails?.csrfToken,
    },
    params: {
      page: page,
      page_size: pageSize,
    },
  };

  axiosPrivate(requestOptions)
    .then((res) => {
      const logs = res?.data?.results?.map((result) => ({
        created_at: result.created_at,
        execution_id: result.id,
        status: result.status,
        execution_time: result.execution_time,
      }));
      setExecutionLogs(logs);
      setExecutionLogsTotalCount(res.data.count);
    })
    .catch((err) => {
      setAlertDetails(handleException(err));
    });
};

export { fetchExecutionLogs };
