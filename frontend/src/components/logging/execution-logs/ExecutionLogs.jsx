import { DatePicker, Flex, Tabs, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useEffect, useState, useRef } from "react";

import { LogsTable } from "../logs-table/LogsTable";
import { DetailedLogs } from "../detailed-logs/DetailedLogs";
import {
  ApiDeployments,
  ETLIcon,
  Workflows,
  Task,
} from "../../../assets/index";
import "./ExecutionLogs.css";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import useRequestUrl from "../../../hooks/useRequestUrl";

function ExecutionLogs() {
  const { RangePicker } = DatePicker;
  const [activeTab, setActiveTab] = useState("ETL");
  const { id } = useParams();
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const navigate = useNavigate();
  const { getUrl } = useRequestUrl();

  const [dataList, setDataList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [selectedDateRange, setSelectedDateRange] = useState([]);
  const [datePickerValue, setDatePickerValue] = useState(null);
  const [ordering, setOrdering] = useState(null);
  const [pollingIds, setPollingIds] = useState(new Set());
  // Store timeouts in a ref for proper cleanup
  const pollingTimeoutsRef = useRef({});
  const currentPath = location.pathname !== `/${sessionDetails?.orgName}/logs`;
  const items = [
    {
      key: "ETL",
      label: "ETL Sessions",
      icon: (
        <ETLIcon
          className={`log-tab-icon ${activeTab === "ETL" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "API",
      label: "API Sessions",
      icon: (
        <ApiDeployments
          className={`log-tab-icon ${activeTab === "API" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "WF",
      label: "Workflow Sessions",
      icon: (
        <Workflows
          className={`log-tab-icon ${activeTab === "WF" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "TASK",
      label: "Task Sessions",
      icon: (
        <Task
          className={`log-tab-icon ${activeTab === "TASK" ? "active" : ""}`}
        />
      ),
    },
  ];
  const onChange = (key) => {
    navigate(`/${sessionDetails?.orgName}/logs`);
    setActiveTab(key);
  };
  const onOk = (value) => {
    if (value && value.length === 2 && value[0] && value[1]) {
      setSelectedDateRange([value[0]?.toISOString(), value[1]?.toISOString()]);
      setDatePickerValue(value);
    }
  };

  // Check if execution should continue polling
  const shouldPoll = (item) => {
    // Only poll EXECUTING or PENDING status
    if (
      item?.status?.toLowerCase() !== "executing" &&
      item?.status?.toLowerCase() !== "pending"
    ) {
      return false;
    }

    // Check if execution is stale (>1 hour from last modification)
    const modifiedAt = new Date(item?.modified_at);
    const now = new Date();
    const oneHourInMs = 60 * 60 * 1000;
    const timeDifference = now - modifiedAt;

    if (timeDifference > oneHourInMs) {
      // Stopping polling in case the execution is possibly stuck
      return false;
    }

    return true;
  };

  // Clear a single polling timeout
  const clearPollingTimeout = (id) => {
    if (pollingTimeoutsRef.current[id]) {
      clearTimeout(pollingTimeoutsRef.current[id]);
      delete pollingTimeoutsRef.current[id];
    }
  };

  // Clear all polling timeouts and reset state
  const clearAllPolling = () => {
    Object.keys(pollingTimeoutsRef.current).forEach((id) => {
      clearTimeout(pollingTimeoutsRef.current[id]);
    });
    pollingTimeoutsRef.current = {};
    setPollingIds(new Set());
  };

  const pollExecutingRecord = async (id) => {
    try {
      const url = getUrl(`/execution/${id}/`);
      const response = await axiosPrivate.get(url);
      const item = response?.data;

      // Update the record in the dataList
      setDataList((prevData) => {
        const newData = [...prevData];
        const index = newData.findIndex((record) => record.key === id);
        if (index !== -1) {
          const total = item.total_files || 0;
          const processed =
            (item?.successful_files || 0) + (item?.failed_files || 0);
          const progress =
            total > 0 ? Math.round((processed / total) * 100) : 0;

          newData[index] = {
            ...newData[index],
            progress,
            processed,
            total,
            success: item?.status === "COMPLETED",
            isError: item?.status === "ERROR",
            workflowName: item?.workflow_name,
            pipelineName: item?.pipeline_name || "Pipeline name not found",
            successfulFiles: item?.successful_files,
            failedFiles: item?.failed_files,
            totalFiles: item?.total_files,
            status: item?.status,
            execution_time: item?.execution_time,
          };

          // If status should no longer be polled, remove from polling
          if (!shouldPoll(item)) {
            setPollingIds((prev) => {
              const newSet = new Set(prev);
              newSet.delete(id);
              return newSet;
            });
            clearPollingTimeout(id);
          }
        }
        return newData;
      });

      // Continue polling if should still poll
      if (shouldPoll(item)) {
        pollingTimeoutsRef.current[id] = setTimeout(
          () => pollExecutingRecord(id),
          5000
        );
      }
    } catch (err) {
      setPollingIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
      clearPollingTimeout(id);
    }
  };

  const startPollingForExecuting = (records) => {
    records.forEach((record) => {
      if (shouldPoll(record) && !pollingIds.has(record.key)) {
        setPollingIds((prev) => {
          const newSet = new Set(prev);
          newSet.add(record.key);
          return newSet;
        });
        pollExecutingRecord(record.key);
      }
    });
  };

  const fetchLogs = async (page) => {
    try {
      setLoading(true);
      const url = getUrl(`/execution/`);
      const response = await axiosPrivate.get(url, {
        params: {
          execution_entity: activeTab,
          page_size: pagination.pageSize,
          page,
          created_at_after: selectedDateRange[0] || null,
          created_at_before: selectedDateRange[1] || null,
          ordering,
        },
      });
      setPagination({
        current: page,
        pageSize: pagination?.pageSize,
        total: response?.data?.count, // Total number of records
      });
      const formattedData = response?.data?.results.map((item) => {
        const total = item.total_files || 0;
        const processed =
          (item?.successful_files || 0) + (item?.failed_files || 0);
        const progress = total > 0 ? Math.round((processed / total) * 100) : 0;
        return {
          key: item?.id,
          executedAt: formattedDateTime(item?.created_at),
          executedAtWithSeconds: formattedDateTimeWithSeconds(item?.created_at),
          executionId: item?.id,
          progress,
          processed,
          success: item?.status === "COMPLETED",
          isError: item?.status === "ERROR",
          workflowName: item?.workflow_name,
          pipelineName: item?.pipeline_name || "Pipeline name not found",
          successfulFiles: item?.successful_files,
          failedFiles: item?.failed_files,
          totalFiles: item?.total_files,
          status: item?.status,
          execution_time: item?.execution_time,
        };
      });
      setDataList(formattedData);
      startPollingForExecuting(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const customButtons = () => {
    return (
      <Flex gap={10} className="log-controls">
        <Tabs
          activeKey={activeTab}
          items={items}
          onChange={onChange}
          className="log-tab"
        />
        <RangePicker
          showTime={{ format: "YYYY-MM-DDTHH:mm:ssZ[Z]" }}
          value={datePickerValue}
          onChange={(value) => {
            setDatePickerValue(value);
            setSelectedDateRange(
              value ? [value[0].toISOString(), value[1].toISOString()] : []
            );
          }}
          onOk={onOk}
          className="logs-date-picker"
          disabled={currentPath}
          format="YYYY-MM-DD HH:mm:ss"
        />
      </Flex>
    );
  };

  // Clear all polling when component unmounts or view changes
  useEffect(() => {
    return clearAllPolling;
  }, [id, activeTab]);

  useEffect(() => {
    if (!currentPath) {
      // Clear any existing polling when fetching new logs
      clearAllPolling();
      setDataList([]);
      fetchLogs(pagination.current);
    }
  }, [activeTab, pagination.current, selectedDateRange, ordering, currentPath]);

  return (
    <>
      <ToolNavBar
        title={"Logs"}
        CustomButtons={customButtons}
        enableSearch={false}
      />
      <div className="file-log-layout">
        {id ? (
          <DetailedLogs />
        ) : (
          <>
            <Typography.Title className="logs-title" level={4}>
              Execution Logs
            </Typography.Title>
            <div className="settings-layout">
              <LogsTable
                tableData={dataList}
                loading={loading}
                pagination={pagination}
                setPagination={setPagination}
                setOrdering={setOrdering}
                activeTab={activeTab}
              />
            </div>
          </>
        )}
      </div>
    </>
  );
}

export { ExecutionLogs };
