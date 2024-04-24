import { Modal, Button } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";
import { useSessionStore } from "../../../store/session-store.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";

const LogsModal = ({ open, setOpen, logRecord }) => {
  const [selectedLogId, setSelectedLogId] = useState(null);
  const [logDescModalOpen, setLogDescModalOpen] = useState(false);
  const [logDetails, setLogDetails] = useState(null);
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

  return (
    <>
      <Modal
        title="Execution Logs"
        centered
        visible={open}
        onCancel={() => setOpen(false)}
        footer={null}
        bodyStyle={{ maxHeight: "60vh", overflowY: "auto" }}
      >
        {logRecord.map((log) => (
          <div key={log.execution_log_id}>
            <p>Created At: {log.created_at}</p>
            <p>
              Execution Log ID:{" "}
              <Button
                type="link"
                onClick={() => handleLogIdClick(log.execution_log_id)}
              >
                {log.execution_log_id}
              </Button>
            </p>
            <p>Status: {log.status}</p>
            <p>Execution Time: {log.execution_time}</p>
            <hr />
          </div>
        ))}
      </Modal>

      <Modal
        title={`Execution Log Details - ${selectedLogId}`}
        centered
        visible={logDescModalOpen}
        onCancel={() => setLogDescModalOpen(false)}
        footer={null}
      >
        <pre>{JSON.stringify(logDetails, null, 2)}</pre>
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
