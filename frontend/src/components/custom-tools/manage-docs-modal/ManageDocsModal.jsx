import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Divider,
  Modal,
  Radio,
  Table,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./ManageDocsModal.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function ManageDocsModal({
  open,
  setOpen,
  generateIndex,
  handleUpdateTool,
  handleDocChange,
}) {
  const [isUploading, setIsUploading] = useState(false);
  const [rows, setRows] = useState([]);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const {
    selectedDoc,
    listOfDocs,
    updateCustomTool,
    details,
    defaultLlmProfile,
    disableLlmOrDocChange,
  } = useCustomToolStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const columns = [
    {
      title: "Document",
      dataIndex: "document",
      key: "document",
    },
    {
      title: "",
      dataIndex: "reindex",
      key: "reindex",
      width: 30,
    },
    {
      title: "",
      dataIndex: "delete",
      key: "delete",
      width: 30,
    },
    {
      title: "",
      dataIndex: "select",
      key: "select",
      width: 30,
    },
  ];

  useEffect(() => {
    const newRows = listOfDocs.map((doc) => {
      return {
        key: doc,
        document: doc || "",
        reindex: (
          <Tooltip title="Re-Index">
            <Button
              size="small"
              className="display-flex-align-center"
              onClick={() => generateIndex(doc)}
            >
              <ReloadOutlined className="manage-llm-pro-icon" />
            </Button>
          </Tooltip>
        ),
        delete: (
          <ConfirmModal
            handleConfirm={() => handleDelete(doc)}
            content="The document will be permanently deleted."
          >
            <Button
              size="small"
              className="display-flex-align-center"
              disabled={disableLlmOrDocChange?.length > 0}
            >
              <DeleteOutlined className="manage-llm-pro-icon" />
            </Button>
          </ConfirmModal>
        ),
        select: (
          <Radio
            checked={selectedDoc === doc}
            onClick={() => handleDocChange(doc)}
            disabled={disableLlmOrDocChange?.length > 0}
          />
        ),
      };
    });
    setRows(newRows);
  }, [listOfDocs, selectedDoc, disableLlmOrDocChange]);

  const beforeUpload = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const fileName = file.name;
        const fileAlreadyExists = [...listOfDocs].includes(fileName);
        if (!fileAlreadyExists) {
          resolve(file);
        } else {
          setAlertDetails({
            type: "error",
            content: "File name already exists",
          });
          reject(new Error("File name already exists"));
        }
      };
    });
  };

  const handleUploadChange = async (info) => {
    if (info.file.status === "uploading") {
      setIsUploading(true);
    }

    if (info.file.status === "done") {
      setIsUploading(false);
      setAlertDetails({
        type: "success",
        content: "File uploaded successfully",
      });

      const docName = info?.file?.name;
      const newListOfDocs = [...listOfDocs];
      newListOfDocs.push(docName);
      setOpen(false);
      await generateIndex(info?.file?.name);
      const body = {
        selectedDoc: docName,
        listOfDocs: newListOfDocs,
      };
      updateCustomTool(body);
      handleUpdateTool({ output: docName });
    } else if (info.file.status === "error") {
      setIsUploading(false);
      setAlertDetails({
        type: "error",
        content: "Failed to upload",
      });
    }
  };

  const handleDelete = (docName) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/file/delete?file_name=${docName}&tool_id=${details?.tool_id}`,
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const newListOfDocs = [...listOfDocs].filter(
          (item) => item !== docName
        );
        updateCustomTool({ listOfDocs: newListOfDocs });

        if (docName === selectedDoc) {
          updateCustomTool({ selectedDoc: "" });
          handleUpdateTool({ output: "" });
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to delete"));
      });
  };

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      maskClosable={false}
    >
      <div className="pre-post-amble-body">
        <SpaceWrapper>
          <div>
            <Typography.Text className="add-cus-tool-header">
              Manage Documents
            </Typography.Text>
          </div>
          <div>
            <Upload
              name="file"
              action={`/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/upload?tool_id=${details?.tool_id}`}
              headers={{
                "X-CSRFToken": sessionDetails.csrfToken,
              }}
              onChange={handleUploadChange}
              disabled={isUploading || !defaultLlmProfile}
              showUploadList={false}
              accept=".pdf"
              beforeUpload={beforeUpload}
            >
              <Tooltip
                title={
                  !defaultLlmProfile &&
                  "Set the default LLM profile before uploading a document"
                }
              >
                <Button
                  className="width-100"
                  icon={<PlusOutlined />}
                  type="text"
                  block
                  loading={isUploading}
                  disabled={
                    !defaultLlmProfile || disableLlmOrDocChange?.length > 0
                  }
                >
                  Upload New File
                </Button>
              </Tooltip>
            </Upload>
          </div>
          <Divider className="manage-docs-div" />
          <SpaceWrapper>
            <div>
              <Typography.Text strong>Uploaded files</Typography.Text>
            </div>
            {!listOfDocs || listOfDocs?.length === 0 ? (
              <EmptyState text="Upload the document" />
            ) : (
              <div>
                <Table
                  columns={columns}
                  dataSource={rows}
                  size="small"
                  bordered
                  pagination={{ pageSize: 10 }}
                />
              </div>
            )}
          </SpaceWrapper>
        </SpaceWrapper>
      </div>
    </Modal>
  );
}

ManageDocsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  generateIndex: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
  handleDocChange: PropTypes.func.isRequired,
};
export { ManageDocsModal };
