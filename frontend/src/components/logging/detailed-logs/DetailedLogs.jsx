import { useEffect, useState, useRef } from "react";
import PropTypes from "prop-types";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeftOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  CloseCircleFilled,
  CopyOutlined,
  EyeOutlined,
  FileTextOutlined,
  HourglassOutlined,
  InfoCircleFilled,
  MoreOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Checkbox,
  Dropdown,
  Flex,
  Table,
  Tooltip,
  Typography,
  Input,
} from "antd";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DetailedLogs.css";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";
import { LogModal } from "../log-modal/LogModal";
import { FilterIcon } from "../filter-dropdown/FilterDropdown";
import { LogsRefreshControls } from "../logs-refresh-controls/LogsRefreshControls";
import useRequestUrl from "../../../hooks/useRequestUrl";

// Component for status message with conditional tooltip (only when truncated)
const StatusMessageCell = ({ text }) => {
  const textRef = useRef(null);
  const [isOverflowing, setIsOverflowing] = useState(false);

  useEffect(() => {
    const checkOverflow = () => {
      if (textRef.current) {
        setIsOverflowing(
          textRef.current.scrollWidth > textRef.current.clientWidth
        );
      }
    };
    checkOverflow();
    window.addEventListener("resize", checkOverflow);
    return () => window.removeEventListener("resize", checkOverflow);
  }, [text]);

  const content = (
    <span ref={textRef} className="status-message-text">
      {text}
    </span>
  );

  return isOverflowing ? <Tooltip title={text}>{content}</Tooltip> : content;
};

StatusMessageCell.propTypes = {
  text: PropTypes.string,
};

const DetailedLogs = () => {
  const { id, type } = useParams(); // Get the ID from the URL
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const navigate = useNavigate();
  const { getUrl } = useRequestUrl();

  const [executionDetails, setExecutionDetails] = useState();
  const [executionFiles, setExecutionFiles] = useState();
  const [loading, setLoading] = useState();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [logDescModalOpen, setLogDescModalOpen] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [ordering, setOrdering] = useState(null);
  const [columnsVisibility, setColumnsVisibility] = useState({});
  const [statusFilter, setStatusFilter] = useState(null);
  const [searchText, setSearchText] = useState("");
  const [searchTimeout, setSearchTimeout] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const autoRefreshIntervalRef = useRef(null);

  const filterOptions = ["COMPLETED", "PENDING", "ERROR", "EXECUTING"];
  const TERMINAL_STATES = ["COMPLETED", "ERROR", "STOPPED"];

  // Check if execution is in a terminal state (no more updates expected)
  const isTerminalState =
    executionDetails?.status &&
    TERMINAL_STATES.includes(executionDetails.status.toUpperCase());

  const handleCopyToClipboard = (text, label = "Text") => {
    navigator.clipboard.writeText(text).then(() => {
      setAlertDetails({
        type: "success",
        content: `${label} copied to clipboard`,
      });
    });
  };

  const fetchExecutionDetails = async (id) => {
    try {
      const url = getUrl(`/execution/${id}/`);
      const response = await axiosPrivate.get(url);
      const item = response?.data;
      const total = item?.total_files || 0;
      const processed =
        (item?.successful_files || 0) + (item?.failed_files || 0);
      const progress = total > 0 ? Math.round((processed / total) * 100) : 0;
      const formattedData = {
        executedAt: formattedDateTime(item?.created_at),
        executionId: item?.id,
        progress,
        processed,
        total,
        status: item?.status,
        executionName: item?.workflow_name,
        ranFor: item?.execution_time,
        executedAtWithSeconds: formattedDateTimeWithSeconds(item?.created_at),
        successfulFiles: item?.successful_files,
        failedFiles: item?.failed_files,
        totalFiles: item?.total_files,
      };

      setExecutionDetails(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const fetchExecutionFiles = async (id, page, customParams = null) => {
    // Helper function to process API response
    function processResponse(response) {
      const formattedData = response?.data?.results.map((item, index) => {
        return {
          key: `${index.toString()}-${item?.id}`,
          fileName: item?.file_name,
          statusMessage: item?.status_msg || "Yet to be processed",
          fileSize: item?.file_size,
          status: item?.status,
          executedAt: formattedDateTime(item?.created_at),
          executionTime: item?.execution_time,
          executionId: item?.id,
          executedAtWithSeconds: formattedDateTimeWithSeconds(item?.created_at),
          filePath: item?.file_path,
        };
      });

      setExecutionFiles(formattedData);
    }

    try {
      const url = getUrl(`/execution/${id}/files/`);
      const defaultParams = {
        page_size: pagination.pageSize,
        page,
        ordering,
        file_name: searchText.trim() || null,
      };
      const params = { ...defaultParams, ...customParams };
      const searchParams = new URLSearchParams();

      for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined) {
          searchParams.append(key, value);
        }
      }

      // Handle file status filter for MultipleChoiceFilter
      if (statusFilter && statusFilter.length > 0) {
        for (const status of statusFilter) {
          searchParams.append("status", status);
        }
      }

      const response = await axiosPrivate.get(
        `${url}?${searchParams.toString()}`
      );
      setPagination({
        current: page,
        pageSize: pagination.pageSize,
        total: response?.data?.count,
      });
      processResponse(response);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (value) => {
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }

    setSearchText(value);

    const timeoutId = setTimeout(() => {
      const params = {
        file_name: value.trim() || null,
      };
      fetchExecutionFiles(id, pagination.current, params);
    }, 1000);

    setSearchTimeout(timeoutId);
  };

  useEffect(() => {
    return () => {
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }
    };
  }, [searchTimeout]);

  // Column width strategy:
  // - Fixed px for predictable content (timestamps, status, file size, execution time, action)
  // - Percentage for variable content (file name 12%, status message 30%, file path 20%)
  // - Status Message gets most space as it contains the most important variable info
  const columnsDetailedTable = [
    {
      title: "Executed At",
      dataIndex: "executedAt",
      key: "executedAt",
      width: 140,
      sorter: true,
      render: (_, record) => (
        <Tooltip title={record.executedAtWithSeconds}>
          {record.executedAt}
        </Tooltip>
      ),
    },
    {
      title: "File Name",
      dataIndex: "fileName",
      key: "fileName",
      width: "12%",
      ellipsis: true,
      filterDropdown: () => (
        <div className="search-container">
          <Input
            placeholder="Search files"
            value={searchText}
            onChange={(e) => handleSearch(e.target.value)}
            className="search-input"
          />
        </div>
      ),
      filterIcon: () => (
        <SearchOutlined style={{ color: searchText ? "#1890ff" : undefined }} />
      ),
    },
    {
      title: "Status Message",
      dataIndex: "statusMessage",
      key: "statusMessage",
      width: "30%",
      ellipsis: true,
      render: (text) => <StatusMessageCell text={text} />,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 110,
      filters: filterOptions.map((filter) => ({
        text: filter,
        value: filter,
      })),
      filterIcon: (filtered) => <FilterIcon filtered={filtered} />,
    },
    {
      title: "File Size",
      dataIndex: "fileSize",
      key: "fileSize",
      width: 70,
      sorter: true,
    },
    ...(type !== "API"
      ? [
          {
            title: "File Path",
            dataIndex: "filePath",
            key: "filePath",
            width: "20%",
            ellipsis: true,
          },
        ]
      : []),
    {
      title: "Execution Time",
      dataIndex: "executionTime",
      key: "executionTime",
      width: 90,
      sorter: true,
    },
    {
      title: "Action",
      dataIndex: "action",
      key: "action",
      width: 60,
      render: (_, record) => (
        <Tooltip title="View logs">
          <Button
            icon={<EyeOutlined />}
            onClick={() => handleLogsModalOpen(record)}
          ></Button>
        </Tooltip>
      ),
    },
  ];

  const handleTableChange = (newPagination, filters, sorter) => {
    setPagination((prev) => ({
      ...prev,
      current: newPagination.current,
      pageSize: newPagination.pageSize,
    }));

    if (sorter.order) {
      const fieldMap = {
        executedAt: "created_at",
        fileSize: "file_size",
        executionTime: "execution_time",
      };
      const backendField = fieldMap[sorter.field] || sorter.field;
      const order =
        sorter.order === "ascend" ? backendField : `-${backendField}`;
      setOrdering(order);
    } else {
      setOrdering(null);
    }
    if (filters?.status) {
      setStatusFilter(filters.status);
    } else {
      setStatusFilter(null);
    }
  };

  const handleLogsModalOpen = (record) => {
    setLogDescModalOpen(true);
    setSelectedRecord(record);
  };

  const handleRefresh = () => {
    fetchExecutionDetails(id);
    fetchExecutionFiles(id, pagination.current);
  };

  useEffect(() => {
    fetchExecutionDetails(id);
    fetchExecutionFiles(id, pagination.current);
  }, [pagination.current, pagination.pageSize, ordering, statusFilter]);

  // Auto-disable auto-refresh when execution reaches terminal state
  useEffect(() => {
    if (isTerminalState && autoRefresh) {
      setAutoRefresh(false);
    }
  }, [isTerminalState]);

  // Auto-refresh interval management
  useEffect(() => {
    if (autoRefreshIntervalRef.current) {
      clearInterval(autoRefreshIntervalRef.current);
      autoRefreshIntervalRef.current = null;
    }

    if (autoRefresh) {
      autoRefreshIntervalRef.current = setInterval(() => {
        fetchExecutionDetails(id);
        fetchExecutionFiles(id, pagination.current);
      }, 30000);
    }

    return () => {
      if (autoRefreshIntervalRef.current) {
        clearInterval(autoRefreshIntervalRef.current);
        autoRefreshIntervalRef.current = null;
      }
    };
  }, [autoRefresh, id, pagination.current]);

  useEffect(() => {
    const initialColumns = columnsDetailedTable.reduce((acc, col) => {
      acc[col.key] = true;
      return acc;
    }, {});
    setColumnsVisibility(initialColumns);
  }, []);

  const handleColumnToggle = (key) => {
    setColumnsVisibility((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };
  const menu = {
    items: columnsDetailedTable.map((col) => ({
      key: col.key,
      label: (
        <Checkbox
          checked={columnsVisibility[col.key]}
          onChange={() => handleColumnToggle(col.key)}
        >
          {col.title}
        </Checkbox>
      ),
    })),
  };

  const columnsToShow = columnsDetailedTable
    .filter((col) => columnsVisibility[col.key])
    .map((col) => {
      if (col.key === "action") {
        return {
          ...col,
          width: 80,
          align: "center",
          title: () => (
            <div className="action-column-header">
              <span>Action</span>
              <Dropdown menu={menu} trigger={["click"]} placement="bottomRight">
                <span className="column-settings-trigger">
                  <MoreOutlined className="column-settings-icon" />
                </span>
              </Dropdown>
            </div>
          ),
        };
      }
      return col;
    });

  return (
    <div className="detailed-logs-container">
      <div className="detailed-logs-header">
        <Typography.Title className="logs-title" level={4}>
          <Button
            type="text"
            shape="circle"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(`/${sessionDetails?.orgName}/logs`)}
          />
          {type} Execution ID {id}
          <Button
            className="copy-btn-outlined"
            icon={<CopyOutlined />}
            onClick={() => handleCopyToClipboard(id, "Execution ID")}
          />
        </Typography.Title>
        <LogsRefreshControls
          autoRefresh={autoRefresh}
          setAutoRefresh={setAutoRefresh}
          onRefresh={handleRefresh}
          disabled={isTerminalState}
        />
      </div>
      <Flex
        align="center"
        justify="space-between"
        className="detailed-logs-cards"
      >
        <Flex className="pad-12">
          <Card className="logs-details-card">
            <Flex justify="flex-start" align="center">
              <CalendarOutlined className="logging-card-icons" />
              <div>
                <Typography className="logging-card-title">Started</Typography>
                <Tooltip title={executionDetails?.executedAtWithSeconds}>
                  <Typography>{executionDetails?.executedAt}</Typography>
                </Tooltip>
              </div>
            </Flex>
          </Card>
          <Card className="logs-details-card">
            <Flex justify="flex-start" align="center">
              <ClockCircleOutlined className="logging-card-icons" />
              <div>
                <Typography className="logging-card-title">
                  {executionDetails?.status.toLowerCase() === "executing"
                    ? "Running for"
                    : "Ran for"}
                </Typography>
                <Typography>{executionDetails?.ranFor}</Typography>
              </div>
            </Flex>
          </Card>
          <Card className="logs-details-card">
            <Flex justify="flex-start" align="center">
              <FileTextOutlined className="logging-card-icons" />
              <div>
                <Typography className="logging-card-title">
                  {executionDetails?.status.toLowerCase() === "executing"
                    ? "Processing files"
                    : "Processed files"}{" "}
                  -{" "}
                  <Tooltip title="Total files">
                    <span className="status-container">
                      <FileTextOutlined className="gen-index-progress" />{" "}
                      {executionDetails?.totalFiles}
                    </span>
                  </Tooltip>
                </Typography>
                <span>
                  <Tooltip title="Successful files">
                    <span className="status-container">
                      <InfoCircleFilled className="gen-index-success" />{" "}
                      {executionDetails?.successfulFiles}
                    </span>
                  </Tooltip>
                  <Tooltip title="Failed files">
                    <span className="status-container">
                      <CloseCircleFilled className="gen-index-fail" />{" "}
                      {executionDetails?.failedFiles}
                    </span>
                  </Tooltip>
                  <Tooltip title="In Progress files">
                    {executionDetails?.totalFiles -
                      (executionDetails?.successfulFiles +
                        executionDetails?.failedFiles) >
                      0 && (
                      <span className="status-container">
                        <HourglassOutlined className="gen-index-progress" />{" "}
                        {executionDetails?.totalFiles -
                          (executionDetails?.successfulFiles +
                            executionDetails?.failedFiles)}
                      </span>
                    )}
                  </Tooltip>
                </span>
              </div>
            </Flex>
          </Card>
        </Flex>
        <Button
          className="view-log-button"
          icon={<EyeOutlined />}
          onClick={() => handleLogsModalOpen({})}
        >
          View Logs
        </Button>
      </Flex>
      <div className="detailed-logs-table-container">
        <Table
          dataSource={executionFiles}
          columns={columnsToShow}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            pageSizeOptions: ["10", "20", "50", "100"],
            showTotal: (total, range) =>
              `${range[0]}-${range[1]} of ${total} files`,
          }}
          bordered
          size="small"
          loading={loading}
          onChange={handleTableChange}
          sortDirections={["ascend", "descend", "ascend"]}
        />
      </div>
      <LogModal
        executionId={id}
        fileId={selectedRecord?.executionId}
        logDescModalOpen={logDescModalOpen}
        setLogDescModalOpen={setLogDescModalOpen}
        filterParams={{ executionTime: "event_time" }}
      />
    </div>
  );
};
export { DetailedLogs };
