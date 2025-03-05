import { DatePicker, Tabs, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { LogsTable } from "../logs-table/LogsTable";
import { TopBar } from "../../widgets/top-bar/TopBar";
import { DetailedLogs } from "../detailed-logs/DetailedLogs";
import { ApiDeployments, CustomToolIcon, ETLIcon } from "../../../assets/index";
import "./ExecutionLogs.css";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";

function ExecutionLogs() {
  const { RangePicker } = DatePicker;
  const [activeTab, setActiveTab] = useState("ETL"); // State to track the active tab
  const { id } = useParams(); // Get the ID from the URL
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const navigate = useNavigate();

  const [dataList, setDataList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [selectedDateRange, setSelectedDateRange] = useState([]);
  const [ordering, setOrdering] = useState(null);
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
        <ApiDeployments
          className={`log-tab-icon ${activeTab === "WF" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "TASK",
      label: "Task Sessions",
      icon: (
        <CustomToolIcon
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
    }
  };

  const fetchLogs = async (page) => {
    try {
      setLoading(true);
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/`;
      const response = await axiosPrivate.get(url, {
        params: {
          execution_entity: activeTab,
          page_size: pagination.pageSize,
          page,
          start_date: selectedDateRange[0] || null,
          end_date: selectedDateRange[1] || null,
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
          total,
          success: item?.status === "COMPLETED",
          isError: item?.status === "ERROR",
          workflowName: item?.workflow_name,
          pipelineName: item?.pipeline_name || "Pipeline name not found",
          successfulFiles: item?.successful_files,
          failedFiles: item?.failed_files,
        };
      });
      setDataList(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs(pagination.current);
  }, [activeTab, pagination.current, selectedDateRange, ordering]);

  return (
    <div className="file-logs-container">
      <TopBar enableSearch={false} title="Logs">
        <Tabs activeKey={activeTab} items={items} onChange={onChange} />
        <RangePicker
          showTime={{ format: "YYYY-MM-DDTHH:mm:ssZ[Z]" }}
          onChange={(value) =>
            setSelectedDateRange(
              value ? [value[0].toISOString(), value[1].toISOString()] : []
            )
          }
          onOk={onOk}
          className="logs-date-picker"
          disabled={currentPath}
        />
      </TopBar>
      <IslandLayout>
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
      </IslandLayout>
    </div>
  );
}

export { ExecutionLogs };
