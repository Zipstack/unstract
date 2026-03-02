import { DatePicker, Tabs } from "antd";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ApiDeployments,
  ETLIcon,
  Task,
  Workflows,
} from "../../../assets/index";
import { DetailedLogs } from "../detailed-logs/DetailedLogs";
import { LogsRefreshControls } from "../logs-refresh-controls/LogsRefreshControls";
import { LogsTable } from "../logs-table/LogsTable";
import "./ExecutionLogs.css";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import useRequestUrl from "../../../hooks/useRequestUrl";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";

function ExecutionLogs() {
  const { RangePicker } = DatePicker;
  const [activeTab, setActiveTab] = useState("ETL");
  const { id } = useParams();
  const location = useLocation();
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
  const [executionIdSearch, setExecutionIdSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const autoRefreshIntervalRef = useRef(null);
  const currentPath = location.pathname !== `/${sessionDetails?.orgName}/logs`;

  // Compute back route - use location state if available, otherwise default to logs listing
  const backRoute = id
    ? location.state?.from || `/${sessionDetails?.orgName}/logs`
    : null;

  // State to pass back for scroll restoration
  const backRouteState =
    id && location.state?.scrollToCardId
      ? {
          scrollToCardId: location.state.scrollToCardId,
          cardExpanded: location.state.cardExpanded,
        }
      : null;

  const items = [
    {
      key: "ETL",
      label: "ETL Executions",
      icon: (
        <ETLIcon
          className={`log-tab-icon ${activeTab === "ETL" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "API",
      label: "API Executions",
      icon: (
        <ApiDeployments
          className={`log-tab-icon ${activeTab === "API" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "WF",
      label: "Workflow Executions",
      icon: (
        <Workflows
          className={`log-tab-icon ${activeTab === "WF" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "TASK",
      label: "Task Executions",
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
          id: executionIdSearch || null,
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
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const customButtons = () => {
    return (
      <Tabs
        activeKey={activeTab}
        items={items}
        onChange={onChange}
        className="log-tab"
      />
    );
  };

  useEffect(() => {
    if (!currentPath) {
      setDataList([]);
      fetchLogs(pagination.current);
    }
  }, [
    activeTab,
    pagination.current,
    pagination.pageSize,
    selectedDateRange,
    ordering,
    executionIdSearch,
    currentPath,
  ]);

  // Auto-refresh interval management
  useEffect(() => {
    if (autoRefreshIntervalRef.current) {
      clearInterval(autoRefreshIntervalRef.current);
      autoRefreshIntervalRef.current = null;
    }

    if (autoRefresh) {
      autoRefreshIntervalRef.current = setInterval(() => {
        fetchLogs(pagination.current);
      }, 30000);
    }

    return () => {
      if (autoRefreshIntervalRef.current) {
        clearInterval(autoRefreshIntervalRef.current);
        autoRefreshIntervalRef.current = null;
      }
    };
  }, [autoRefresh, pagination.current]);

  // Clear auto-refresh when tab changes
  useEffect(() => {
    setAutoRefresh(false);
  }, [activeTab]);

  return (
    <>
      <ToolNavBar
        title={"Execution Logs"}
        CustomButtons={customButtons}
        enableSearch={false}
        previousRoute={backRoute}
        previousRouteState={backRouteState}
      />
      <div className="file-log-layout">
        {id ? (
          <DetailedLogs />
        ) : (
          <>
            <div className="logs-header">
              <div className="logs-filter-controls">
                <RangePicker
                  showTime={{ format: "YYYY-MM-DDTHH:mm:ssZ[Z]" }}
                  value={datePickerValue}
                  onChange={(value) => {
                    setDatePickerValue(value);
                    setSelectedDateRange(
                      value?.[0] && value?.[1]
                        ? [value[0].toISOString(), value[1].toISOString()]
                        : [],
                    );
                  }}
                  onOk={onOk}
                  className="logs-date-picker"
                  format="YYYY-MM-DD HH:mm:ss"
                />
                <LogsRefreshControls
                  autoRefresh={autoRefresh}
                  setAutoRefresh={setAutoRefresh}
                  onRefresh={() => fetchLogs(pagination.current)}
                />
              </div>
            </div>
            <div className="logs-table-container">
              <LogsTable
                tableData={dataList}
                loading={loading}
                pagination={pagination}
                setPagination={setPagination}
                setOrdering={setOrdering}
                activeTab={activeTab}
                executionIdSearch={executionIdSearch}
                setExecutionIdSearch={setExecutionIdSearch}
              />
            </div>
          </>
        )}
      </div>
    </>
  );
}

export { ExecutionLogs };
