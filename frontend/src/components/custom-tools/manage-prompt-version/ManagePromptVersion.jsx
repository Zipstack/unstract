import { Modal, Space, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

// import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
// import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
// import { useAlertStore } from "../../../store/alert-store";
// import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
// import { EmptyState } from "../../widgets/empty-state/EmptyState";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
// import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./ManagePromptVersion.css";

function ManagePromptVersion({ open, setOpen }) {
  const [rows, setRows] = useState([]);
  // const axiosPrivate = useAxiosPrivate();
  // const handleException = useExceptionHandler();

  useEffect(() => {
    setRows([]);
  }, []);

  const columns = [
    {
      title: "Version",
      dataIndex: "version",
      key: "version",
      width: 500,
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
    },
    {
      title: "",
      dataIndex: "load",
      key: "load",
      width: 80,
    },
  ];

  // const handleDelete = (tagId) => {
  //   const requestOptions = {
  //     method: "GET",
  //     url: `/api/v1/unstract/${sessionDetails?.orgId}/file/delete?document_id=${docId}&tool_id=${details?.tool_id}`,
  //   };

  //   axiosPrivate(requestOptions)
  //     .then(() => {
  //       const newListOfDocs = [...listOfDocs].filter(
  //         (item) => item?.document_id !== docId
  //       );
  //       updateCustomTool({ listOfDocs: newListOfDocs });

  //       if (docId === selectedDoc?.document_id) {
  //         updateCustomTool({ selectedDoc: "" });
  //         handleUpdateTool({ output: "" });
  //       }
  //     })
  //     .catch((err) => {
  //       setAlertDetails(handleException(err, "Failed to delete"));
  //     });
  // };

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      maskClosable={false}
      width={1000}
    >
      <div className="pre-post-amble-body">
        {/* <div> */}
        <SpaceWrapper>
          <Space>
            <Typography.Text className="add-cus-tool-header">
              Prompt Version Manager
            </Typography.Text>
          </Space>
          <div>
            <Table
              columns={columns}
              dataSource={rows}
              size="small"
              bordered
              pagination={{ pageSize: 10 }}
            />
          </div>
        </SpaceWrapper>
      </div>
    </Modal>
  );
}

ManagePromptVersion.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};
export { ManagePromptVersion };
