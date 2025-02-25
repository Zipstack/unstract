import { Table, Tooltip } from "antd";
import "./LogsTable.css";
import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

const LogsTable = ({ tableData, loading, pagination, setPagination }) => {
  const navigate = useNavigate();
  const columns = [
    {
      title: "Executed At",
      dataIndex: "executedAt",
      key: "executedAt",
    },
    {
      title: "Execution ID",
      dataIndex: "executionId",
      key: "executionId",
      render: (text) => (
        <a
          style={{ wordBreak: "break-all" }}
          onClick={() => navigate(`${text}`)}
        >
          {text}
        </a>
      ),
    },
    {
      title: "Execution Name",
      dataIndex: "executionName",
      key: "executionName",
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

  return (
    <Table
      columns={columns}
      dataSource={tableData}
      pagination={{
        ...pagination,
        onChange: (page) => {
          setPagination((prev) => {
            return { ...prev, current: page };
          });
        },
      }}
      bordered
      size="small"
      loading={loading}
    />
  );
};

LogsTable.propTypes = {
  tableData: PropTypes.array,
  loading: PropTypes.bool,
  pagination: PropTypes.object,
  setPagination: PropTypes.func,
};

export { LogsTable };
