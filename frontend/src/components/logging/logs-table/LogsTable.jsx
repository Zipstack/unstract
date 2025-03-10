import { Table, Tooltip, Typography } from "antd";
import "./LogsTable.css";
import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

const LogsTable = ({
  tableData,
  loading,
  pagination,
  setPagination,
  setOrdering,
  activeTab,
}) => {
  const navigate = useNavigate();
  const columns = [
    {
      title: "Executed At",
      dataIndex: "executedAt",
      key: "executedAt",
      showSorterTooltip: { target: "full-header" },
      sorter: true,
      render: (_, record) => (
        <Tooltip title={record.executedAtWithSeconds}>
          {record.executedAt}
        </Tooltip>
      ),
    },
    {
      title: "Execution ID",
      dataIndex: "executionId",
      key: "executionId",
      render: (text) => (
        <Typography.Link
          className="title-name-redirect"
          onClick={() => navigate(`${activeTab}/${text}`)}
        >
          {text}
        </Typography.Link>
      ),
    },
    {
      title: "Execution Name",
      dataIndex: "pipelineName",
      key: "executionName",
      render: (_, record) => (
        <>
          <Typography.Text strong>{record?.pipelineName}</Typography.Text>
          <br />
          <Typography.Text type="secondary" className="p-or-d-typography">
            from {record?.workflowName}
          </Typography.Text>
        </>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (_, record) => (
        <span>
          <Tooltip title="Successful files">
            <span>{record?.successfulFiles} ✅</span>
          </Tooltip>
          {" / "}
          <Tooltip title="Failed files">
            <span>{record?.failedFiles} ❌</span>
          </Tooltip>
          {" / "}
          <Tooltip title="Total files">
            <span>{record?.total} 📜</span>
          </Tooltip>
        </span>
      ),
    },
    {
      title: "Files Processed",
      dataIndex: "filesProcessed",
      key: "filesProcessed",
      render: (text, record) => `${record?.processed}/${record?.total}`,
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
  };

  return (
    <Table
      columns={columns}
      dataSource={tableData}
      pagination={pagination}
      bordered
      size="small"
      loading={loading}
      onChange={handleTableChange}
      scroll={{
        y: 55 * 10,
      }}
    />
  );
};

LogsTable.propTypes = {
  tableData: PropTypes.array,
  loading: PropTypes.bool,
  pagination: PropTypes.object,
  setPagination: PropTypes.func,
  setOrdering: PropTypes.func,
  activeTab: PropTypes.string,
};

export { LogsTable };
