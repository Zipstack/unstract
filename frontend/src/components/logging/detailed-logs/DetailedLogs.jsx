import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  CalendarOutlined,
  ClockCircleOutlined,
  DownOutlined,
  EyeOutlined,
  FileTextOutlined,
  FilterOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Checkbox,
  Dropdown,
  Flex,
  Radio,
  Space,
  Table,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DetailedLogs.css";
import {
  formatSecondsToHMS,
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";
import { LogModal } from "../log-modal/LogModal";

const DetailedLogs = () => {
  const { id, type } = useParams(); // Get the ID from the URL
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

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
        ranFor: formatSecondsToHMS(item?.execution_time),
        executedAtWithSeconds: formattedDateTimeWithSeconds(item?.created_at),
      };

      setExecutionDetails(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const fetchExecutionFiles = async (id, page) => {
    try {
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/${id}/files/`;
      const response = await axiosPrivate.get(url, {
        params: {
          page_size: pagination.pageSize,
          page,
          ordering,
          status: statusFilter,
        },
      });
      // Replace with your actual API URL
      setPagination({
        current: page,
        pageSize: pagination?.pageSize,
        total: response?.data?.count, // Total number of records
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
  const handleClearFilter = (confirm) => {
    setStatusFilter(null);
    confirm();
  };

  const columnsDetailedTable = [
    {
      title: "File Name",
      dataIndex: "fileName",
      key: "fileName",
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
      filterDropdown: (props) => (
        <FilterDropdown {...props} handleClearFilter={handleClearFilter} />
      ),
      filteredValue: statusFilter ? [statusFilter] : [],
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
      title: "File Path",
      dataIndex: "filePath",
      key: "filePath",
    },
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
      // Determine ascending or descending order
      const order = sorter.order === "ascend" ? "created_at" : "-created_at";
      setOrdering(order);
    } else {
      setOrdering(null); // Default ordering if sorting is cleared
    }
    if (filters?.status) {
      setStatusFilter(filters.status[0]);
    }
  };

  const handleLogsModalOpen = (record) => {
    setLogDescModalOpen(true);
    setSelectedRecord(record);
  };

  useEffect(() => {
    fetchExecutionDetails(id);
    fetchExecutionFiles(id, pagination.current);
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
                <Typography className="logging-card-title">Ran for</Typography>
                <Typography>{executionDetails?.ranFor}</Typography>
              </div>
            </Flex>
          </Card>
          <Card className="logs-details-card">
            <Flex justify="flex-start" align="center">
              <FileTextOutlined className="logging-card-icons" />
              <div>
                <Typography className="logging-card-title">
                  Processed files
                </Typography>
                <Typography>
                  {executionDetails?.processed}/{executionDetails?.total}{" "}
                  {executionDetails?.processed > 0 && "Successfully"}
                </Typography>
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
        <Dropdown menu={menu} trigger={["click"]}>
          <Button icon={<DownOutlined />}>Show/Hide Columns</Button>
        </Dropdown>
        <Table
          dataSource={executionFiles}
          columns={columnsToShow}
          pagination={{ ...pagination }}
          loading={loading}
          onChange={handleTableChange}
        />
      </div>
      <LogModal
        executionId={id}
        fileId={selectedRecord?.executionId}
        logDescModalOpen={logDescModalOpen}
        setLogDescModalOpen={setLogDescModalOpen}
      />
    </>
  );
};

const FilterIcon = ({ filtered }) => (
  <FilterOutlined style={{ color: filtered ? "#1677ff" : undefined }} />
);

const FilterDropdown = ({
  setSelectedKeys,
  selectedKeys,
  confirm,
  handleClearFilter,
}) => (
  <div style={{ padding: 8 }}>
    <Radio.Group
      onChange={(e) => {
        setSelectedKeys(e.target.value ? [e.target.value] : []);
        confirm();
      }}
      value={selectedKeys[0] || null}
    >
      <Space direction="vertical">
        <Radio value="COMPLETED">COMPLETED</Radio>
        <Radio value="PENDING">PENDING</Radio>
        <Radio value="ERROR">ERROR</Radio>
        <Radio value="QUEUED">QUEUED</Radio>
        <Radio value="INITIATED">INITIATED</Radio>
        <Radio value="EXECUTING">EXECUTING</Radio>
        <Radio value="STOPPED">STOPPED</Radio>
      </Space>
    </Radio.Group>
    <br />
    <Button
      className="clear-button"
      type="primary"
      size="small"
      onClick={() => handleClearFilter(confirm)}
    >
      Clear
    </Button>
  </div>
);

FilterIcon.propTypes = {
  filtered: PropTypes.bool,
};

FilterDropdown.propTypes = {
  setSelectedKeys: PropTypes.func,
  selectedKeys: PropTypes.any,
  confirm: PropTypes.func,
  handleClearFilter: PropTypes.func,
};

export { DetailedLogs };
