import {
  Table,
  Modal,
  Button,
  Select,
  InputNumber,
  Input,
  Space,
  Typography,
  Popconfirm,
  Tag,
  Tooltip,
  Row,
  Col,
  message,
} from "antd";
import {
  DeleteOutlined,
  ReloadOutlined,
  FilterOutlined,
  ClearOutlined,
  CopyOutlined,
  ExclamationCircleFilled,
} from "@ant-design/icons";
import PropTypes from "prop-types";
import { useState, useEffect } from "react";

import { workflowService } from "../../workflows/workflow/workflow-service.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { copyToClipboard } from "../../../helpers/GetStaticData";
import "./FileHistoryModal.css";

const { Text } = Typography;

const MAX_BULK_DELETE = 100;

const FileHistoryModal = ({ open, setOpen, workflowId, workflowName }) => {
  const [fileHistories, setFileHistories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState([]);
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const workflowApiService = workflowService();

  // Filter states
  const [statusFilter, setStatusFilter] = useState([]);
  const [executionCountMin, setExecutionCountMin] = useState(null);
  const [executionCountMax, setExecutionCountMax] = useState(null);
  const [filePathFilter, setFilePathFilter] = useState("");

  // Bulk delete confirmation states
  const [showBulkDeleteConfirm, setShowBulkDeleteConfirm] = useState(false);
  const [fetchingCount, setFetchingCount] = useState(false);
  const [bulkDeleteCount, setBulkDeleteCount] = useState(0);

  // Track applied filter values (used for data fetching, pagination, and bulk clear)
  // These are separate from input values to prevent fetching with unapplied filters
  const [appliedFilters, setAppliedFilters] = useState({
    status: [],
    executionCountMin: null,
    executionCountMax: null,
    filePath: "",
  });

  // Pagination states
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const statusOptions = [
    { label: "Error", value: "ERROR" },
    { label: "Completed", value: "COMPLETED" },
  ];

  // Check if filters have been applied (for "Clear with Filters" button)
  const hasAppliedFilters = Boolean(
    appliedFilters.status?.length > 0 ||
      appliedFilters.executionCountMin !== null ||
      appliedFilters.executionCountMax !== null ||
      appliedFilters.filePath
  );

  // Check if input values differ from applied values (for Apply button indicator)
  const hasUnappliedChanges = (() => {
    // Compare status arrays (order-independent)
    const statusEqual =
      statusFilter.length === appliedFilters.status.length &&
      statusFilter.every((s) => appliedFilters.status.includes(s));

    return (
      !statusEqual ||
      executionCountMin !== appliedFilters.executionCountMin ||
      executionCountMax !== appliedFilters.executionCountMax ||
      filePathFilter !== appliedFilters.filePath
    );
  })();

  // Copy to clipboard helper
  const handleCopy = async (text, label = "Text") => {
    const success = await copyToClipboard(text);
    if (success) {
      message.success(`${label} copied to clipboard!`);
    } else {
      message.error("Failed to copy to clipboard");
    }
  };

  // Fetch file histories with optional filters parameter
  // If filters are passed, use them; otherwise use appliedFilters from state
  const fetchFileHistoriesWithFilters = async (
    page = 1,
    pageSize = 10,
    filters = null
  ) => {
    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content: "Workflow ID is missing. Unable to fetch file histories.",
      });
      return;
    }

    const filtersToUse = filters || appliedFilters;

    setLoading(true);
    try {
      const params = {
        page,
        page_size: pageSize,
      };

      // Use provided filters for data fetching
      if (filtersToUse.status?.length > 0) {
        params.status = filtersToUse.status.join(",");
      }
      if (
        filtersToUse.executionCountMin !== null &&
        filtersToUse.executionCountMin !== undefined
      ) {
        params.execution_count_min = filtersToUse.executionCountMin;
      }
      if (
        filtersToUse.executionCountMax !== null &&
        filtersToUse.executionCountMax !== undefined
      ) {
        params.execution_count_max = filtersToUse.executionCountMax;
      }
      if (filtersToUse.filePath) {
        params.file_path = filtersToUse.filePath;
      }

      const response = await workflowApiService.getFileHistories(
        workflowId,
        params
      );

      const data = response?.data?.results || [];
      setFileHistories(data);
      setPagination({
        current: page,
        pageSize: pageSize,
        total: response?.data?.count || 0,
      });
    } catch (err) {
      // Extract more detailed error message
      const errorMessage =
        err?.response?.data?.message ||
        err?.response?.data?.error ||
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to fetch file histories";

      setAlertDetails({
        type: "error",
        content: errorMessage,
      });
    } finally {
      setLoading(false);
    }
  };

  // Alias for backward compatibility (pagination, refresh, etc.)
  const fetchFileHistories = (page, pageSize) =>
    fetchFileHistoriesWithFilters(page, pageSize);

  // Load data on open or filter change
  useEffect(() => {
    if (open && workflowId) {
      fetchFileHistories(1, pagination.pageSize);
      setSelectedRowKeys([]);
    }
  }, [open, workflowId]);

  // Handle filter apply
  const handleApplyFilters = () => {
    // Save current input values as applied filters
    const newFilters = {
      status: statusFilter,
      executionCountMin: executionCountMin,
      executionCountMax: executionCountMax,
      filePath: filePathFilter,
    };
    setAppliedFilters(newFilters);
    // Pass new filters directly (state update is async, so can't rely on appliedFilters yet)
    fetchFileHistoriesWithFilters(1, pagination.pageSize, newFilters);
    setSelectedRowKeys([]);
  };

  // Handle filter reset
  const handleResetFilters = () => {
    setStatusFilter([]);
    setExecutionCountMin(null);
    setExecutionCountMax(null);
    setFilePathFilter("");
    // Reset applied filters
    const emptyFilters = {
      status: [],
      executionCountMin: null,
      executionCountMax: null,
      filePath: "",
    };
    setAppliedFilters(emptyFilters);
    // Fetch with empty filters
    fetchFileHistoriesWithFilters(1, pagination.pageSize, emptyFilters);
  };

  // Handle pagination change
  const handleTableChange = (paginationConfig) => {
    fetchFileHistories(paginationConfig.current, paginationConfig.pageSize);
  };

  // Delete single file history
  const handleDeleteSingle = async (fileHistoryId) => {
    try {
      await workflowApiService.deleteFileHistory(workflowId, fileHistoryId);
      setAlertDetails({
        type: "success",
        message: "File history deleted successfully",
      });
      // Refresh data
      fetchFileHistories(pagination.current, pagination.pageSize);
      setSelectedRowKeys([]);
    } catch (err) {
      setAlertDetails(handleException(err));
    }
  };

  // Delete selected file histories (bulk delete by IDs)
  const handleDeleteSelected = async () => {
    if (selectedRowKeys.length === 0) return;

    if (selectedRowKeys.length > MAX_BULK_DELETE) {
      setAlertDetails({
        type: "error",
        content: `Cannot delete more than ${MAX_BULK_DELETE} items at once. Please select fewer items.`,
      });
      return;
    }

    setLoading(true);
    try {
      const response = await workflowApiService.bulkDeleteFileHistoriesByIds(
        workflowId,
        selectedRowKeys
      );

      setAlertDetails({
        type: "success",
        message:
          response?.data?.message ||
          `${selectedRowKeys.length} file histories deleted successfully`,
      });

      // Refresh data
      fetchFileHistories(pagination.current, pagination.pageSize);
      setSelectedRowKeys([]);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  // Prepare bulk clear - fetch count for confirmation using applied filters
  const handlePrepareBulkClear = async () => {
    setFetchingCount(true);
    try {
      const params = {
        page: 1,
        page_size: 1, // We only need count, not actual data
      };

      // Use applied filters (not input values)
      if (appliedFilters.status?.length > 0) {
        params.status = appliedFilters.status.join(",");
      }
      if (
        appliedFilters.executionCountMin !== null &&
        appliedFilters.executionCountMin !== undefined
      ) {
        params.execution_count_min = appliedFilters.executionCountMin;
      }
      if (
        appliedFilters.executionCountMax !== null &&
        appliedFilters.executionCountMax !== undefined
      ) {
        params.execution_count_max = appliedFilters.executionCountMax;
      }
      if (appliedFilters.filePath) {
        params.file_path = appliedFilters.filePath;
      }

      const response = await workflowApiService.getFileHistories(
        workflowId,
        params
      );

      const count = response?.data?.count || 0;
      if (count > 0) {
        setBulkDeleteCount(count);
        setShowBulkDeleteConfirm(true);
      }
      // Note: count === 0 case is handled by disabling the button when pagination.total === 0
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setFetchingCount(false);
    }
  };

  // Perform bulk clear after user confirms using applied filters
  const performBulkClear = async () => {
    setShowBulkDeleteConfirm(false);
    setLoading(true);
    try {
      const filters = {};

      // Use applied filters (not input values)
      if (appliedFilters.status?.length > 0) {
        filters.status = appliedFilters.status;
      }
      if (
        appliedFilters.executionCountMin !== null &&
        appliedFilters.executionCountMin !== undefined
      ) {
        filters.execution_count_min = appliedFilters.executionCountMin;
      }
      if (
        appliedFilters.executionCountMax !== null &&
        appliedFilters.executionCountMax !== undefined
      ) {
        filters.execution_count_max = appliedFilters.executionCountMax;
      }
      if (appliedFilters.filePath) {
        filters.file_path = appliedFilters.filePath;
      }

      const response = await workflowApiService.bulkClearFileHistories(
        workflowId,
        filters
      );

      setAlertDetails({
        type: "success",
        message:
          response?.data?.message ||
          `${response?.data?.deleted_count} file histories cleared`,
      });

      // Refresh data
      fetchFileHistories(1, pagination.pageSize);
      setSelectedRowKeys([]);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  // Row selection config
  const rowSelection = {
    selectedRowKeys,
    onChange: (selectedKeys) => {
      setSelectedRowKeys(selectedKeys);
    },
  };

  // Table columns
  const columns = [
    {
      title: "File Path",
      dataIndex: "file_path",
      key: "file_path",
      width: "40%",
      ellipsis: true,
      render: (text) => (
        <Space size="small" className="cell-content">
          <Text ellipsis={{ tooltip: text }} className="file-path-text">
            {text || "N/A"}
          </Text>
          {text && (
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleCopy(text, "File path");
              }}
              title="Copy file path"
            />
          )}
        </Space>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: "8%",
      render: (status) => {
        let color = "default";
        if (status === "SUCCESS" || status === "COMPLETED") {
          color = "success";
        } else if (status === "ERROR" || status === "FAILURE") {
          color = "error";
        } else if (status === "PROCESSING") {
          color = "processing";
        } else if (status === "PENDING") {
          color = "warning";
        }
        return <Tag color={color}>{status}</Tag>;
      },
    },
    {
      title: (
        <Tooltip title="Number of times this file has been processed in this workflow">
          <span>Total Attempts</span>
        </Tooltip>
      ),
      dataIndex: "execution_count",
      key: "execution_count",
      width: "10%",
      render: (count, record) => {
        const max = record?.max_execution_count;
        const exceeded = record?.has_exceeded_limit;
        return (
          <Text type={exceeded ? "danger" : "secondary"}>
            {count} / {max || "∞"}
          </Text>
        );
      },
    },
    {
      title: "Last Attempt",
      dataIndex: "modified_at",
      key: "modified_at",
      width: "12%",
      responsive: ["md"],
      render: (date) => {
        if (!date) return "N/A";
        return new Date(date).toLocaleString();
      },
    },
    {
      title: "Error",
      dataIndex: "error",
      key: "error",
      width: "25%",
      ellipsis: true,
      responsive: ["md"],
      render: (error) =>
        error ? (
          <Space size="small" className="cell-content">
            <Text
              type="danger"
              ellipsis={{ tooltip: error }}
              className="error-text"
            >
              {error}
            </Text>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleCopy(error, "Error message");
              }}
              title="Copy error message"
            />
          </Space>
        ) : (
          "-"
        ),
    },
    {
      title: "Action",
      key: "action",
      width: "8%",
      render: (_, record) => (
        <Popconfirm
          title="Delete this file history?"
          description="This action cannot be undone."
          onConfirm={() => handleDeleteSingle(record.id)}
          okText="Yes"
          cancelText="No"
        >
          <Button type="link" danger icon={<DeleteOutlined />} size="small">
            Delete
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Modal
      title={`File History - ${workflowName || "Workflow"}`}
      centered
      open={open}
      onCancel={() => setOpen(false)}
      footer={null}
      width="90%"
      className="file-history-modal"
    >
      <div className="file-history-content">
        {/* Filters Section */}
        <div className="filters-section">
          <Row gutter={[12, 12]} align="bottom">
            <Col xs={24} sm={12} md={10}>
              <Space direction="vertical" size="small" className="full-width">
                <Text strong className="filter-label">
                  File Path:
                </Text>
                <Input
                  placeholder="Search by file path..."
                  value={filePathFilter}
                  onChange={(e) => setFilePathFilter(e.target.value)}
                  allowClear
                  onPressEnter={handleApplyFilters}
                />
              </Space>
            </Col>
            <Col xs={12} sm={8} md={4}>
              <Space direction="vertical" size="small" className="full-width">
                <Text strong className="filter-label">
                  Status:
                </Text>
                <Select
                  mode="multiple"
                  placeholder="Select status"
                  value={statusFilter}
                  onChange={setStatusFilter}
                  options={statusOptions}
                  className="full-width"
                  allowClear
                />
              </Space>
            </Col>
            <Col xs={6} sm={4} md={3}>
              <Space direction="vertical" size="small" className="full-width">
                <Text strong className="filter-label">
                  Min Attempts:
                </Text>
                <InputNumber
                  placeholder="0"
                  value={executionCountMin}
                  onChange={setExecutionCountMin}
                  min={0}
                  className="full-width"
                />
              </Space>
            </Col>
            <Col xs={6} sm={4} md={3}>
              <Space direction="vertical" size="small" className="full-width">
                <Text strong className="filter-label">
                  Max Attempts:
                </Text>
                <InputNumber
                  placeholder="∞"
                  value={executionCountMax}
                  onChange={setExecutionCountMax}
                  min={executionCountMin || 0}
                  className="full-width"
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={4}>
              <Space size="small" className="full-width">
                <Button
                  type="primary"
                  icon={<FilterOutlined />}
                  onClick={handleApplyFilters}
                  className="flex-button"
                >
                  {hasUnappliedChanges ? "Apply *" : "Apply"}
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={handleResetFilters}
                  className="flex-button"
                >
                  Reset
                </Button>
              </Space>
            </Col>
          </Row>
        </div>

        {/* Action Buttons */}
        <div className="action-buttons">
          <Space wrap>
            <Popconfirm
              title={`Delete ${selectedRowKeys.length} selected file histories?`}
              description="This action cannot be undone."
              onConfirm={handleDeleteSelected}
              okText="Yes"
              cancelText="No"
              disabled={selectedRowKeys.length === 0}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={selectedRowKeys.length === 0}
              >
                Delete Selected ({selectedRowKeys.length})
              </Button>
            </Popconfirm>

            <Button
              icon={<ClearOutlined />}
              onClick={handlePrepareBulkClear}
              loading={fetchingCount}
              disabled={!hasAppliedFilters || pagination.total === 0}
            >
              Clear with Filters
            </Button>

            {/* Clear with Filters confirmation modal */}
            <Modal
              title={
                <Space>
                  <ExclamationCircleFilled className="warning-icon" />
                  <span>Clear with filters</span>
                </Space>
              }
              open={showBulkDeleteConfirm}
              onCancel={() => setShowBulkDeleteConfirm(false)}
              footer={[
                <Button
                  key="cancel"
                  onClick={() => setShowBulkDeleteConfirm(false)}
                >
                  Cancel
                </Button>,
                <Button key="clear" type="primary" onClick={performBulkClear}>
                  Clear
                </Button>,
              ]}
              centered
              width={400}
            >
              <Typography.Text>
                This will delete {bulkDeleteCount} record
                {bulkDeleteCount !== 1 ? "s" : ""} matching the active filters.
                This action cannot be undone.
              </Typography.Text>
            </Modal>

            <Button
              icon={<ReloadOutlined />}
              onClick={() =>
                fetchFileHistories(pagination.current, pagination.pageSize)
              }
            >
              Refresh
            </Button>
          </Space>
        </div>

        {/* Table */}
        <Table
          columns={columns}
          dataSource={fileHistories}
          rowKey="id"
          loading={loading}
          rowSelection={rowSelection}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} records`,
          }}
          onChange={handleTableChange}
          scroll={{ x: 1200, y: "calc(100vh - 450px)" }}
        />
      </div>
    </Modal>
  );
};

FileHistoryModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  workflowId: PropTypes.string,
  workflowName: PropTypes.string,
};

export default FileHistoryModal;
