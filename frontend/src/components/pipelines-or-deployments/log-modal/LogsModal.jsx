import { Table, Modal, Button } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { useSessionStore } from "../../../store/session-store.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";

const LogsModal = ({ open, setOpen, logRecord }) => {
  const [selectedLogId, setSelectedLogId] = useState(null);
  const [logDescModalOpen, setLogDescModalOpen] = useState(false);
  const [logDetails, setLogDetails] = useState([]);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const fetchLogDetails = async (logId) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/execution/${logId}/logs/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const logDetails = res.data.results.map((item) => ({
          id: item.id,
          log: item.data.log,
          type: item.data.type,
          event_time: item.event_time,
        }));
        setLogDetails(logDetails);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const handleLogIdClick = (logId) => {
    setSelectedLogId(logId);
    fetchLogDetails(logId);
    setLogDescModalOpen(true);
  };

  const logColumns = [
    {
      title: "Created At",
      dataIndex: "created_at",
      key: "created_at",
    },
    {
      title: "Execution Log ID",
      dataIndex: "execution_log_id",
      key: "execution_log_id",
      render: (text, record) => (
        <Button
          type="link"
          onClick={() => handleLogIdClick(record.execution_log_id)}
        >
          {text}
        </Button>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
    },
    {
      title: "Execution Time",
      dataIndex: "execution_time",
      key: "execution_time",
    },
  ];

  const logDetailsColumns = [
    {
      title: "Log",
      dataIndex: "log",
      key: "log",
    },
    {
      title: "Event Time",
      dataIndex: "event_time",
      key: "event_time",
    },
  ];
  return (
    <>
      <Modal
        title="Execution Logs"
        centered
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width="80%"
      >
        <Table columns={logColumns} dataSource={logRecord} rowKey="id" />
      </Modal>

      <Modal
        title={`Execution Log Details - ${selectedLogId}`}
        centered
        open={logDescModalOpen}
        onCancel={() => setLogDescModalOpen(false)}
        footer={null}
        width="80%"
        wrapClassName="modal-body"
      >
        <Table
          columns={logDetailsColumns}
          dataSource={logDetails}
          rowKey="id"
        />
      </Modal>
    </>
  );
};

LogsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  logRecord: PropTypes.array.isRequired,
};

export { LogsModal };
