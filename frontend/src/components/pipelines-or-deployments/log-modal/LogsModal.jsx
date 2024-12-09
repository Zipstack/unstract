import { Table, Modal, Button } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { useSessionStore } from "../../../store/session-store.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import "./LogsModel.css";
import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown.jsx";

const LogsModal = ({
  open,
  setOpen,
  logRecord,
  totalLogs,
  fetchExecutionLogs,
}) => {
  const [selectedLogId, setSelectedLogId] = useState(null);
  const [logDescModalOpen, setLogDescModalOpen] = useState(false);
  const [logDetails, setLogDetails] = useState([]);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const [totalCount, setTotalCount] = useState(0);

  const fetchLogDetails = async (logId, page = 1, pageSize = 10) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/execution/${logId}/logs/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      params: {
        page: page,
        page_size: pageSize,
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const logDetails = res?.data?.results?.map((item) => ({
          id: item?.id,
          log: <CustomMarkdown text={item?.data?.log} />,
          type: item?.data?.type,
          stage: item?.data?.stage,
          level: item?.data?.level,
          event_time: item?.event_time,
        }));
        setLogDetails(logDetails);
        setTotalCount(res?.data?.count);
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
      title: "Executed At",
      dataIndex: "created_at",
      key: "created_at",
    },
    {
      title: "Execution ID",
      dataIndex: "execution_id",
      key: "execution_id",
      render: (text, record) => {
        return (
          <Button
            type="link"
            onClick={() => handleLogIdClick(record?.execution_id)}
          >
            {text}
          </Button>
        );
      },
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (level) => <span className={level?.toLowerCase()}>{level}</span>,
    },
  ];

  const logDetailsColumns = [
    {
      title: "Event Time",
      dataIndex: "event_time",
      key: "event_time",
    },
    {
      title: "Event Stage",
      dataIndex: "stage",
      key: "stage",
    },
    {
      title: "Log Level",
      dataIndex: "level",
      key: "level",
      render: (level) => <span className={level?.toLowerCase()}>{level}</span>,
    },
    {
      title: "Log",
      dataIndex: "log",
      key: "log",
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
        <Table
          columns={logColumns}
          dataSource={logRecord}
          rowKey="id"
          align="left"
          pagination={{
            total: totalLogs,
            onChange: (page, pageSize) => {
              fetchExecutionLogs(page, pageSize);
            },
          }}
        />
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
          align="left"
          pagination={{
            pageSize: 10,
            total: totalCount,
            onChange: (page, pageSize) => {
              fetchLogDetails(selectedLogId, page, pageSize);
            },
          }}
        />
      </Modal>
    </>
  );
};

LogsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  logRecord: PropTypes.array.isRequired,
  totalLogs: PropTypes.number.isRequired,
  fetchExecutionLogs: PropTypes.func.isRequired,
};

export { LogsModal };
