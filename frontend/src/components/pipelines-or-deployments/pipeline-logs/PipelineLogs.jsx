import { useState, useEffect, useRef } from "react";
import { Modal, Typography, Button } from "antd";
import PropTypes from "prop-types";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";

const { Paragraph } = Typography;

const modalStyle = {
  borderRadius: "8px",
  padding: "0px 0px 24px 0px",
};

const logBoxStyle = {
  width: "96%",
  minHeight: "80%",
  maxHeight: "90%",
  overflow: "auto",
  scrollBehavior: "smooth",
};

const PipelineLogs = ({ open, logRow, closeModal }) => {
  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState("");
  const pollInterval = 2000;
  const boxRef = useRef(null);

  useEffect(() => {
    if (boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    async function fetchLogs() {
      // Add logic to fetch the log messages
      setLogs("");
      setStatus("");
    }

    let intervalId = "";

    if (open) {
      fetchLogs();
      intervalId = setInterval(fetchLogs, pollInterval);
    } else {
      clearInterval(intervalId);
    }

    if (status !== "InProgress") {
      clearInterval(intervalId);
    }

    return () => clearInterval(intervalId);
  }, [open, status]);

  return (
    <Modal
      title="Logs"
      open={open}
      onCancel={closeModal}
      footer={[
        <Button key="close" onClick={closeModal}>
          Close
        </Button>,
      ]}
      style={modalStyle}
    >
      <div>
        <Paragraph>
          <strong>Status:</strong> {status}
        </Paragraph>
        <div ref={boxRef} style={logBoxStyle}>
          {logs.length > 0 && <SyntaxHighlighter>{logs}</SyntaxHighlighter>}
        </div>
      </div>
    </Modal>
  );
};

PipelineLogs.propTypes = {
  open: PropTypes.bool.isRequired,
  closeModal: PropTypes.func.isRequired,
  logRow: PropTypes.object.isRequired,
};

export default PipelineLogs;
