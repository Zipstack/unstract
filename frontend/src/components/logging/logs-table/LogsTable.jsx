import { Table, Tooltip, Typography } from "antd";
import "./LogsTable.css";
import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";
import {
  CloseCircleFilled,
  HourglassOutlined,
  InfoCircleFilled,
} from "@ant-design/icons";

import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { logsStaticContent } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";

const LogsTable = ({
  tableData,
  loading,
  pagination,
  setPagination,
  setOrdering,
  activeTab,
}) => {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
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
      render: (_, record) =>
        activeTab === "WF" ? (
          <Typography.Text strong>{record?.workflowName}</Typography.Text>
        ) : (
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
            <span className="status-container">
              <InfoCircleFilled className="gen-index-success" />{" "}
              {record?.successfulFiles}
            </span>
          </Tooltip>
          <Tooltip title="Failed files">
            <span className="status-container">
              <CloseCircleFilled className="gen-index-fail" />{" "}
              {record?.failedFiles}
            </span>
          </Tooltip>
          <Tooltip title="Queued files">
            {record?.totalFiles -
              (record?.successfulFiles + record?.failedFiles) >
              0 && (
              <span className="status-container">
                <HourglassOutlined className="gen-index-progress" />{" "}
                {record?.totalFiles -
                  (record?.successfulFiles + record?.failedFiles)}
              </span>
            )}
          </Tooltip>
        </span>
      ),
    },
    {
      title: "Files Processed",
      dataIndex: "filesProcessed",
      key: "filesProcessed",
      render: (text, record) => `${record?.processed}/${record?.totalFiles}`,
    },
    {
      title: "Execution Time",
      dataIndex: "executionTime",
      key: "executionTime",
      render: (_, record) => record?.execution_time || "-",
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
      setPagination((prev) => {
        return { ...prev, ...pagination, current: 1 };
      });
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
      sortDirections={["ascend", "descend", "ascend"]}
      scroll={{ y: 55 * 10 }}
      locale={{
        emptyText: (
          <EmptyState
            text={`Currently you have no ${logsStaticContent[activeTab].addBtn}`}
            btnText={`Add ${logsStaticContent[activeTab].addBtn}`}
            handleClick={() =>
              navigate(
                `/${sessionDetails?.orgName}/${logsStaticContent[activeTab].route}`
              )
            }
          />
        ),
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
