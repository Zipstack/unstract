import { Button, Modal, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import "./OutputForDocModal.css";
import { CheckCircleFilled, CloseCircleFilled } from "@ant-design/icons";

const columns = [
  {
    title: "Document",
    dataIndex: "document",
    key: "document",
  },
  {
    title: "Value",
    dataIndex: "value",
    key: "value",
  },
];

function OutputForDocModal({
  open,
  setOpen,
  promptId,
  promptKey,
  profileManagerId,
}) {
  const [rows, setRows] = useState([]);
  const { details, listOfDocs } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  useEffect(() => {
    handleGetOutputForDocs();
  }, [open]);

  const handleGetOutputForDocs = () => {
    if (!profileManagerId) {
      setRows([]);
      return;
    }
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-output/?tool_id=${details?.tool_id}&prompt_id=${promptId}&profile_manager=${profileManagerId}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];
        data.sort((a, b) => {
          return new Date(b.created_at) - new Date(a.created_at);
        });
        handleRowsGeneration(data);
      })
      .catch((err) => {
        throw err;
      });
  };

  const handleRowsGeneration = (data) => {
    const rowsData = [];
    [...listOfDocs].forEach((item) => {
      const output = data.find((outputValue) => outputValue?.doc_name === item);
      const isSuccess = output?.output?.length > 0;
      const content = isSuccess ? output?.output : "Failed";

      const result = {
        key: item,
        document: item,
        value: (
          <Typography.Text>
            <span style={{ marginRight: "8px" }}>
              {isSuccess ? (
                <CheckCircleFilled style={{ color: "#52C41A" }} />
              ) : (
                <CloseCircleFilled style={{ color: "#FF4D4F" }} />
              )}
            </span>{" "}
            {content}
          </Typography.Text>
        ),
      };
      rowsData.push(result);
    });
    setRows(rowsData);
  };

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      width={1000}
      onCancel={() => setOpen(false)}
      footer={null}
      centered
      maskClosable={false}
    >
      <div className="pre-post-amble-body output-doc-layout">
        <div>
          <Typography.Text className="add-cus-tool-header">
            {promptKey}
          </Typography.Text>
        </div>
        <div className="output-doc-gap" />
        <div className="display-flex-right">
          <Button size="small">View in Output Analyzer</Button>
        </div>
        <div className="output-doc-gap" />
        <div className="output-doc-table">
          <Table
            columns={columns}
            dataSource={rows}
            pagination={{ pageSize: 5 }}
          />
        </div>
      </div>
    </Modal>
  );
}

OutputForDocModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  promptId: PropTypes.string.isRequired,
  promptKey: PropTypes.string.isRequired,
  profileManagerId: PropTypes.string.isRequired,
};

export { OutputForDocModal };
