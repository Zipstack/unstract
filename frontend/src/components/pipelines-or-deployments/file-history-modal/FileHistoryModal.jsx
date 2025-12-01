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
} from "@ant-design/icons";
import PropTypes from "prop-types";
import { useState, useEffect } from "react";

import { workflowService } from "../../workflows/workflow/workflow-service.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
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
  const [bulkDeleteCount, setBulkDeleteCount] = useState(0);
  const [fetchingCount, setFetchingCount] = useState(false);

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

  // Copy to clipboard helper
  const copyToClipboard = async (text, label = "Text") => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(`${label} copied to clipboard!`);
    } catch (err) {
      console.error("Failed to copy:", err);
      message.error("Failed to copy to clipboard");
    }
  };

  // Fetch file histories
  const fetchFileHistories = async (page = 1, pageSize = 10) => {
    if (!workflowId) {
      console.error("FileHistoryModal: workflowId is missing");
      return;
    }

    console.log("Fetching file histories:", {
      workflowId,
      page,
      pageSize,
      filters: {
        statusFilter,
        executionCountMin,
        executionCountMax,
        filePathFilter,
      },
    });

    setLoading(true);
    try {
      const params = {
        page,
        page_size: pageSize,
      };

      if (statusFilter?.length > 0) {
        params.status = statusFilter.join(",");
      }
      if (executionCountMin !== null && executionCountMin !== undefined) {
        params.execution_count_min = executionCountMin;
      }
      if (executionCountMax !== null && executionCountMax !== undefined) {
        params.execution_count_max = executionCountMax;
      }
      if (filePathFilter) {
        params.file_path = filePathFilter;
      }

      const response = await workflowApiService.getFileHistories(
        workflowId,
        params
      );

      console.log("File histories response:", response);

      const data = response?.data?.results || [];
      setFileHistories(data);
      setPagination({
        current: page,
        pageSize: pageSize,
        total: response?.data?.count || 0,
      });
    } catch (err) {
      console.error("Error fetching file histories:", err);
      console.error("Error details:", {
        message: err?.message,
        response: err?.response,
        status: err?.response?.status,
        data: err?.response?.data,
      });

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

  // Load data on open or filter change
  useEffect(() => {
    if (open && workflowId) {
      fetchFileHistories(1, pagination.pageSize);
      setSelectedRowKeys([]);
    }
  }, [open, workflowId]);

  // Handle filter apply
  const handleApplyFilters = () => {
    fetchFileHistories(1, pagination.pageSize);
    setSelectedRowKeys([]);
  };

  // Handle filter reset
  const handleResetFilters = () => {
    setStatusFilter([]);
    setExecutionCountMin(null);
    setExecutionCountMax(null);
    setFilePathFilter("");
    // Reset will trigger effect to fetch unfiltered data
    setTimeout(() => {
      fetchFileHistories(1, pagination.pageSize);
    }, 0);
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

  // Prepare bulk clear - fetch count for confirmation
  const handlePrepareBulkClear = async () => {
    setFetchingCount(true);
    try {
      const params = {
        page: 1,
        page_size: 1, // We only need count, not actual data
      };

      if (statusFilter?.length > 0) {
        params.status = statusFilter.join(",");
      }
      if (executionCountMin !== null && executionCountMin !== undefined) {
        params.execution_count_min = executionCountMin;
      }
      if (executionCountMax !== null && executionCountMax !== undefined) {
        params.execution_count_max = executionCountMax;
      }
      if (filePathFilter) {
        params.file_path = filePathFilter;
      }

      const response = await workflowApiService.getFileHistories(
        workflowId,
        params
      );

      const count = response?.data?.count || 0;
      setBulkDeleteCount(count);
      setShowBulkDeleteConfirm(true);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setFetchingCount(false);
    }
  };

  // Perform bulk clear after user confirms
  const performBulkClear = async () => {
    setShowBulkDeleteConfirm(false);
    setLoading(true);
    try {
      const filters = {};

      if (statusFilter?.length > 0) {
        filters.status = statusFilter;
      }
      if (executionCountMin !== null && executionCountMin !== undefined) {
        filters.execution_count_min = executionCountMin;
      }
      if (executionCountMax !== null && executionCountMax !== undefined) {
        filters.execution_count_max = executionCountMax;
      }
      if (filePathFilter) {
        filters.file_path = filePathFilter;
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
        <Space size="small" style={{ width: "100%" }}>
          <Text ellipsis={{ tooltip: text }} style={{ flex: 1, maxWidth: 400 }}>
            {text || "N/A"}
          </Text>
          {text && (
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                copyToClipboard(text, "File path");
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
      title: "Execution Count",
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
      title: "Last Run",
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
          <Space size="small" style={{ width: "100%" }}>
            <Text
              type="danger"
              ellipsis={{ tooltip: error }}
              style={{ flex: 1, maxWidth: 230 }}
            >
              {error}
            </Text>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                copyToClipboard(error, "Error message");
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
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <Text strong style={{ fontSize: "13px" }}>
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
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <Text strong style={{ fontSize: "13px" }}>
                  Status:
                </Text>
                <Select
                  mode="multiple"
                  placeholder="Select status"
                  value={statusFilter}
                  onChange={setStatusFilter}
                  options={statusOptions}
                  style={{ width: "100%" }}
                  allowClear
                />
              </Space>
            </Col>
            <Col xs={6} sm={4} md={3}>
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <Text strong style={{ fontSize: "13px" }}>
                  Min Count:
                </Text>
                <InputNumber
                  placeholder="0"
                  value={executionCountMin}
                  onChange={setExecutionCountMin}
                  min={0}
                  style={{ width: "100%" }}
                />
              </Space>
            </Col>
            <Col xs={6} sm={4} md={3}>
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <Text strong style={{ fontSize: "13px" }}>
                  Max Count:
                </Text>
                <InputNumber
                  placeholder="∞"
                  value={executionCountMax}
                  onChange={setExecutionCountMax}
                  min={executionCountMin || 0}
                  style={{ width: "100%" }}
                />
              </Space>
            </Col>
            <Col xs={24} sm={12} md={4}>
              <Space size="small" style={{ width: "100%" }}>
                <Button
                  type="primary"
                  icon={<FilterOutlined />}
                  onClick={handleApplyFilters}
                  style={{ flex: 1 }}
                >
                  Apply
                </Button>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={handleResetFilters}
                  style={{ flex: 1 }}
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

            <Popconfirm
              open={showBulkDeleteConfirm}
              title={`Delete ${bulkDeleteCount} file ${
                bulkDeleteCount === 1 ? "history" : "histories"
              } matching current filters?`}
              description="This action cannot be undone. Are you sure?"
              onConfirm={performBulkClear}
              onCancel={() => setShowBulkDeleteConfirm(false)}
              okText="Yes, Delete"
              cancelText="Cancel"
              okButtonProps={{ danger: true }}
            >
              <Button
                icon={<ClearOutlined />}
                onClick={handlePrepareBulkClear}
                loading={fetchingCount}
              >
                Clear with Filters
              </Button>
            </Popconfirm>

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
