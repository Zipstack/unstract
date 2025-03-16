import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeftOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  CloseCircleFilled,
  DownOutlined,
  EyeOutlined,
  FileTextOutlined,
  HourglassOutlined,
  InfoCircleFilled,
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

const DetailedLogs = () => {
  const { id, type } = useParams(); // Get the ID from the URL
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const navigate = useNavigate();

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
  const [pollingInterval, setPollingInterval] = useState(null);

  const filterOptions = ["COMPLETED", "PENDING", "ERROR", "EXECUTING"];

  const fetchExecutionDetails = async (id) => {
    try {
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/${id}`;
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

      // Start or stop polling based on status
      if (item?.status === "EXECUTING") {
        if (!pollingInterval) {
          const interval = setInterval(() => {
            fetchExecutionDetails(id);
            fetchExecutionFiles(id, pagination.current);
          }, 5000); // Poll every 5 seconds
          setPollingInterval(interval);
        }
      } else {
        if (pollingInterval) {
          clearInterval(pollingInterval);
          setPollingInterval(null);
        }
      }
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const fetchExecutionFiles = async (id, page, customParams = null) => {
    try {
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/${id}/files/`;
      const defaultParams = {
        page_size: pagination.pageSize,
        page,
        ordering,
        status: statusFilter || null,
        file_name: searchText.trim() || null,
      };

      const params = customParams || defaultParams;
      const response = await axiosPrivate.get(url, { params });
      setPagination({
        current: page,
        pageSize: pagination.pageSize,
        total: response?.data?.count,
      });
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
        page_size: pagination.pageSize,
        page: pagination.current,
        ordering,
        status: statusFilter || null,
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

  const columnsDetailedTable = [
    {
      title: "Executed At",
      dataIndex: "executedAt",
      key: "executedAt",
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
      filterDropdown: () => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="Search files"
            value={searchText}
            onChange={(e) => handleSearch(e.target.value)}
            style={{ width: 188, marginBottom: 8, display: "block" }}
          />
        </div>
      ),
      filterIcon: (filtered) => (
        <SearchOutlined style={{ color: filtered ? "#1890ff" : undefined }} />
      ),
    },
    {
      title: "Status Message",
      dataIndex: "statusMessage",
      key: "statusMessage",
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
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
    },
    {
      title: "Execution Time",
      dataIndex: "executionTime",
      key: "executionTime",
    },
    ...(type !== "API"
      ? [
          {
            title: "File Path",
            dataIndex: "filePath",
            key: "filePath",
          },
        ]
      : []),
    {
      title: "Action",
      dataIndex: "action",
      key: "action",
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

  const handleTableChange = (pagination, filters, sorter) => {
    setPagination((prev) => {
      return { ...prev, ...pagination };
    });

    if (sorter.order) {
      const order = sorter.order === "ascend" ? "created_at" : "-created_at";
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

  useEffect(() => {
    fetchExecutionDetails(id);
    fetchExecutionFiles(id, pagination.current);

    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
      if (searchTimeout) {
        clearTimeout(searchTimeout);
      }
    };
  }, [pagination.current, ordering, statusFilter]);

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
  const columnsToShow = columnsDetailedTable.filter(
    (col) => columnsVisibility[col.key]
  );
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

  return (
    <>
      <Typography.Title className="logs-title" level={4}>
        <Button
          type="text"
          shape="circle"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(`/${sessionDetails?.orgName}/logs`)}
        />
        {type} Session ID - {id}{" "}
      </Typography.Title>
      <Flex align="center" justify="space-between">
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
                  <Tooltip title="Queued files">
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
          type="link"
          onClick={() => handleLogsModalOpen({})}
        >
          View Logs
        </Button>
      </Flex>
      <div className="settings-layout">
        <Dropdown
          menu={menu}
          trigger={["click"]}
          className="column-filter-dropdown"
        >
          <Button icon={<DownOutlined />}>Show/Hide Columns</Button>
        </Dropdown>
        <Table
          dataSource={executionFiles}
          columns={columnsToShow}
          pagination={{ ...pagination }}
          loading={loading}
          onChange={handleTableChange}
          sortDirections={["ascend", "descend", "ascend"]}
          scroll={{ y: 55 * 10 }}
        />
      </div>
      <LogModal
        executionId={id}
        fileId={selectedRecord?.executionId}
        logDescModalOpen={logDescModalOpen}
        setLogDescModalOpen={setLogDescModalOpen}
        filterParams={{ executionTime: "event_time" }}
      />
    </>
  );
};
export { DetailedLogs };
