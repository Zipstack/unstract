import { Modal, Table } from "antd";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { formattedDateTime } from "../../../helpers/GetStaticData";

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
      width: 200,
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
      render: (level) => <span className={level?.toLowerCase()}>{level}</span>,
    },
    {
      title: "Log",
      dataIndex: "log",
      key: "log",
    },
  ];

  useEffect(() => {
    if (logDescModalOpen) {
      fetchExecutionFileLogs(executionId, fileId, pagination.current);
    }
  }, [logDescModalOpen, pagination.current]);
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
          onChange: (page) => {
            setPagination((prev) => {
              return { ...prev, current: page };
            });
          },
        }}
        loading={loading}
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
