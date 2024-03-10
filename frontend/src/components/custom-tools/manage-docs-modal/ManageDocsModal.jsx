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

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./ManageDocsModal.css";

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
    const newRows = listOfDocs.map((item) => {
      return {
        key: item?.prompt_document_id,
        document: item?.document_name || "",
        reindex: (
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={() => generateIndex(item?.prompt_document_id)}
          />
        ),
        delete: (
          <ConfirmModal
            handleConfirm={() => handleDelete(item?.prompt_document_id)}
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
            checked={
              selectedDoc?.prompt_document_id === item?.prompt_document_id
            }
            onClick={() => handleDocChange(item?.prompt_document_id)}
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
        const fileAlreadyExists = [...listOfDocs].find(
          (item) => item?.document_name === fileName
        );
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

      const data = info.file.response?.data;
      const doc = data?.length > 0 ? data[0] : {};
      const newListOfDocs = [...listOfDocs];
      newListOfDocs.push(doc);
      setOpen(false);
      await generateIndex(doc?.prompt_document_id);
      const body = {
        selectedDoc: doc,
        listOfDocs: newListOfDocs,
      };
      updateCustomTool(body);
      handleUpdateTool({ output: doc?.prompt_document_id });
    } else if (info.file.status === "error") {
      setIsUploading(false);
      setAlertDetails({
        type: "error",
        content: "Failed to upload",
      });
    }
  };

  const handleDelete = (docId) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/file/delete?prompt_document_id=${docId}&tool_id=${details?.tool_id}`,
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const newListOfDocs = [...listOfDocs].filter(
          (item) => item?.prompt_document_id !== docId
        );
        updateCustomTool({ listOfDocs: newListOfDocs });

        if (docId === selectedDoc?.prompt_document_id) {
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
