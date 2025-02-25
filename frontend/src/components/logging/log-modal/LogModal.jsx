import { Button, Modal, Radio, Space, Table, Tooltip } from "antd";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";
import { FilterOutlined } from "@ant-design/icons";

import "./LogModal.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";

function LogModal({
  executionId,
  fileId,
  logDescModalOpen,
  setLogDescModalOpen,
}) {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const [executionLogs, setExecutionLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedLogLevel, setSelectedLogLevel] = useState(null);
  const [ordering, setOrdering] = useState(null);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });

  const fetchExecutionFileLogs = async (executionId, fileId, page) => {
    try {
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/${executionId}/logs/`;
      const response = await axiosPrivate.get(url, {
        params: {
          page_size: pagination.pageSize,
          page,
          file_execution_id: fileId,
          log_level: selectedLogLevel,
          ordering,
        },
      });
      // Replace with your actual API URL
      setPagination({
        current: page,
        pageSize: pagination?.pageSize,
        total: response?.data?.count, // Total number of records
      });
      const formattedData = response?.data?.results.map((item) => {
        return {
          key: item?.id,
          eventTime: formattedDateTime(item?.event_time),
          eventStage: item.data?.stage,
          logLevel: item.data?.level,
          log: item?.data?.log,
          executedAtWithSeconds: formattedDateTimeWithSeconds(item?.created_at),
        };
      });

      setExecutionLogs(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setLogDescModalOpen(false);
    setExecutionLogs([]); // Clear logs
    setPagination({ current: 1, pageSize: 10, total: 0 }); // Reset pagination
  };

  const logDetailsColumns = [
    {
      title: "Event Time",
      dataIndex: "eventTime",
      key: "eventTime",
      sorter: true,
      width: 200,
      render: (_, record) => (
        <Tooltip title={record.executedAtWithSeconds}>
          {record.eventTime}
        </Tooltip>
      ),
    },
    {
      title: "Event Stage",
      dataIndex: "eventStage",
      key: "stage",
    },
    {
      title: "Log Level",
      dataIndex: "logLevel",
      key: "level",
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm }) => (
        <div style={{ padding: 8 }}>
          <Radio.Group
            onChange={(e) => {
              setSelectedKeys(e.target.value ? [e.target.value] : []);
              confirm();
            }}
            value={selectedKeys[0] || null}
          >
            <Space direction="vertical">
              <Radio value="INFO">INFO</Radio>
              <Radio value="WARN">WARN</Radio>
              <Radio value="DEBUG">DEBUG</Radio>
              <Radio value="ERROR">ERROR</Radio>
            </Space>
          </Radio.Group>
          <br />
          <Button
            className="clear-button"
            type="primary"
            size="small"
            onClick={() => handleClearFilter(confirm)}
          >
            clear
          </Button>
        </div>
      ),
      filteredValue: selectedLogLevel ? [selectedLogLevel] : [],
      filterIcon: (filtered) => (
        <FilterOutlined
          style={{
            color: filtered ? "#1677ff" : undefined,
          }}
        />
      ),
      render: (level) => <span className={level?.toLowerCase()}>{level}</span>,
    },
    {
      title: "Log",
      dataIndex: "log",
      key: "log",
    },
  ];

  const handleClearFilter = (confirm) => {
    setSelectedLogLevel(null);
    confirm();
  };

  const handleTableChange = (pagination, filters, sorter) => {
    setPagination((prev) => {
      return { ...prev, ...pagination };
    });

    if (sorter.order) {
      // Determine ascending or descending order
      const order = sorter.order === "ascend" ? "created_at" : "-created_at";
      setOrdering(order);
    } else {
      setOrdering(null);
    }
    setSelectedLogLevel(filters.level[0]);
  };

  useEffect(() => {
    if (logDescModalOpen) {
      fetchExecutionFileLogs(executionId, fileId, pagination.current);
    }
  }, [logDescModalOpen, pagination.current, selectedLogLevel, ordering]);
  return (
    <Modal
      title={`Execution Log Details - ${fileId}`}
      centered
      open={logDescModalOpen}
      onCancel={handleClose}
      footer={null}
      width="80%"
      wrapClassName="modal-body"
      destroyOnClose
    >
      <Table
        columns={logDetailsColumns}
        dataSource={executionLogs}
        rowKey="id"
        align="left"
        pagination={{
          ...pagination,
        }}
        loading={loading}
        onChange={handleTableChange}
      />
    </Modal>
  );
}

LogModal.propTypes = {
  executionId: PropTypes.string,
  fileId: PropTypes.string,
  logDescModalOpen: PropTypes.array,
  setLogDescModalOpen: PropTypes.array,
};

export { LogModal };
