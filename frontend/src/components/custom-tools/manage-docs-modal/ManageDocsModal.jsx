import {
  CheckCircleFilled,
  CloseCircleFilled,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Divider,
  Modal,
  Radio,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import "./ManageDocsModal.css";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useSocketLogsStore } from "../../../store/socket-logs-store";

let SummarizeStatusTitle = null;
try {
  SummarizeStatusTitle =
    require("../../../plugins/summarize-status-title/SummarizeStatusTitle").SummarizeStatusTitle;
} catch {
  // The component will remain null if it is not available
}

let publicIndexApi = null;
try {
  publicIndexApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicIndexApi;
} catch {
  // The component will remain null if it is not available
}
const indexTypes = {
  raw: "RAW",
  summarize: "Summarize",
};

function ManageDocsModal({
  open,
  setOpen,
  generateIndex,
  handleUpdateTool,
  handleDocChange,
}) {
  const [isUploading, setIsUploading] = useState(false);
  const [rows, setRows] = useState([]);
  const [rawLlmProfile, setRawLlmProfile] = useState(null);
  const [isRawDataLoading, setIsRawDataLoading] = useState(false);
  const [summarizeLlmProfile, setSummarizeLlmProfile] = useState(null);
  const [isSummarizeDataLoading, setIsSummarizeDataLoading] = useState(false);
  const [indexMessages, setIndexMessages] = useState({});
  const [lastMessagesUpdate, setLastMessagesUpdate] = useState("");
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const { id } = useParams();
  const {
    selectedDoc,
    listOfDocs,
    llmProfiles,
    updateCustomTool,
    details,
    defaultLlmProfile,
    disableLlmOrDocChange,
    indexDocs,
    rawIndexStatus,
    summarizeIndexStatus,
    isSinglePassExtractLoading,
    isPublicSource,
  } = useCustomToolStore();
  const { logs } = useSocketLogsStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const successIndex = (
    <Typography.Text>
      <span style={{ marginRight: "8px" }}>
        <CheckCircleFilled style={{ color: "#52C41A" }} />
      </span>{" "}
      Indexed
    </Typography.Text>
  );

  const failedIndex = (
    <Typography.Text>
      <span style={{ marginRight: "8px" }}>
        <CloseCircleFilled style={{ color: "#FF4D4F" }} />
      </span>{" "}
      Not Indexed
    </Typography.Text>
  );

  const infoIndex = (indexMessage) => {
    let color = "default";

    if (indexMessage?.level === "INFO") {
      color = "processing";
    }
    if (indexMessage?.level === "ERROR") {
      color = "error";
    }

    if (!indexMessage?.message) {
      return;
    }

    return (
      <Tooltip title={indexMessage?.message || ""}>
        <Tag color={color}>
          <div className="tag-max-width ellipsis">{indexMessage?.message}</div>
        </Tag>
      </Tooltip>
    );
  };

  const failedSummary = (
    <Typography.Text>
      <span style={{ marginRight: "8px" }}>
        <CloseCircleFilled style={{ color: "#FF4D4F" }} />
      </span>{" "}
      Not Summarized
    </Typography.Text>
  );

  useEffect(() => {
    setRawLlmProfile(defaultLlmProfile);
    setSummarizeLlmProfile(details?.summarize_llm_profile);
  }, [defaultLlmProfile, details]);

  useEffect(() => {
    if (!open) {
      return;
    }
    handleGetIndexStatus(rawLlmProfile, indexTypes.raw);
  }, [indexDocs, rawLlmProfile, open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    handleGetIndexStatus(summarizeLlmProfile, indexTypes.summarize);
  }, [indexDocs, summarizeLlmProfile, open]);

  useEffect(() => {
    // Reverse the array to have the latest logs at the beginning
    let newMessages = [...logs].reverse();

    // If there are no new messages, return early
    if (newMessages?.length === 0) {
      return;
    }

    // Get the index of the last message received before the last update
    const lastIndex = [...newMessages].findIndex(
      (item) => item?.timestamp === lastMessagesUpdate
    );

    // If the last update's message is found, keep only the new messages
    if (lastIndex > -1) {
      newMessages = newMessages.slice(0, lastIndex);
    }

    // Filter only INFO and ERROR logs
    newMessages = newMessages.filter(
      (item) => item?.level === "INFO" || item?.level === "ERROR"
    );

    // If there are no new INFO or ERROR messages, return early
    if (newMessages?.length === 0) {
      return;
    }

    const updatedMessages = {};
    // Store the newly received logs in the indexMessages state
    newMessages.forEach((item) => {
      const docName = item?.component?.doc_name;

      // If the message for this document already exists, skip
      if (updatedMessages?.[docName] !== undefined) {
        return;
      }

      // Update the message for this document
      updatedMessages[docName] = {
        message: item?.message || "",
        level: item?.level || "INFO",
      };
    });

    // Update indexMessages state with the newly received messages
    setIndexMessages({ ...indexMessages, ...updatedMessages });

    // Update the timestamp of the last received message
    setLastMessagesUpdate(newMessages[0]?.timestamp);
  }, [logs]);

  const handleLoading = (indexType, value) => {
    if (indexType === indexTypes.raw) {
      setIsRawDataLoading(value);
    }

    if (indexType === indexTypes.summarize) {
      setIsSummarizeDataLoading(value);
    }
  };

  const handleIndexStatus = (indexType, data) => {
    if (indexType === indexTypes.raw) {
      updateCustomTool({ rawIndexStatus: data });
    }

    if (indexType === indexTypes.summarize) {
      updateCustomTool({ summarizeIndexStatus: data });
    }
  };

  const handleIsIndexed = (indexType, data) => {
    let isIndexed = false;
    if (indexType === indexTypes.raw) {
      isIndexed = !!data?.raw_index_id;
    }

    if (indexType === indexTypes.summarize) {
      isIndexed = !!data?.summarize_index_id;
    }

    return isIndexed;
  };

  const handleGetIndexStatus = (llmProfileId, indexType) => {
    if (!llmProfileId) {
      handleIndexStatus(indexType, []);
      return;
    }
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/document-index/?profile_manager=${llmProfileId}`;
    if (isPublicSource) {
      url = publicIndexApi(id, llmProfileId);
    }
    const requestOptions = {
      method: "GET",
      url,
    };

    handleLoading(indexType, true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const indexStatus = data.map((item) => {
          return {
            docId: item?.document_manager,
            isIndexed: handleIsIndexed(indexType, item),
          };
        });

        handleIndexStatus(indexType, indexStatus);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to get index status"));
      })
      .finally(() => {
        handleLoading(indexType, false);
      });
  };

  const getLlmProfileName = (llmProfile) => {
    const llmProfileName = llmProfiles.find(
      (item) => item?.profile_id === llmProfile
    );

    return llmProfileName?.profile_name || "No LLM Profile Selected";
  };

  const columns = [
    {
      title: "Document",
      dataIndex: "document",
      key: "document",
    },
    {
      title: (
        <Space className="w-100">
          <Typography.Text>Raw View</Typography.Text>
          <Typography.Text type="secondary">
            {"(" + getLlmProfileName(rawLlmProfile) + ")"}
          </Typography.Text>
          {isRawDataLoading && <SpinnerLoader />}
        </Space>
      ),
      dataIndex: "index",
      key: "index",
      width: 300,
    },
    {
      title: "Actions",
      dataIndex: "reindex",
      key: "reindex",
      width: 200,
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

  if (SummarizeStatusTitle) {
    columns.splice(2, 0, {
      title: (
        <SummarizeStatusTitle
          profileName={"(" + getLlmProfileName(summarizeLlmProfile) + ")"}
          isLoading={isSummarizeDataLoading}
        />
      ),
      dataIndex: "summary",
      key: "summary",
      width: 300,
    });
  }

  const getIndexStatusMessage = (docId, indexType) => {
    let instance = null;
    let failed = null;
    if (indexType === indexTypes.raw) {
      instance = rawIndexStatus.find((item) => item?.docId === docId);
      failed = failedIndex;
    } else {
      instance = summarizeIndexStatus.find((item) => item?.docId === docId);
      failed = failedSummary;
    }

    return instance?.isIndexed ? successIndex : failed;
  };

  const handleReIndexBtnClick = (item) => {
    generateIndex(item);

    try {
      setPostHogCustomEvent("intent_ps_indexed_file", {
        info: "Clicked on index button",
        document_name: item?.document_name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  useEffect(() => {
    const newRows = listOfDocs.map((item) => {
      return {
        key: item?.document_id,
        document: item?.document_name || "",
        index: getIndexStatusMessage(item?.document_id, indexTypes.raw),
        summary:
          SummarizeStatusTitle &&
          getIndexStatusMessage(item?.document_id, indexTypes.summarize),
        reindex: (
          <Space>
            <div>
              {indexDocs.includes(item?.document_id) ? (
                <SpinnerLoader />
              ) : (
                <Tooltip title="Index">
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={() => handleReIndexBtnClick(item)}
                    disabled={
                      disableLlmOrDocChange?.length > 0 ||
                      isSinglePassExtractLoading ||
                      indexDocs.includes(item?.document_id) ||
                      isUploading ||
                      !defaultLlmProfile ||
                      isPublicSource
                    }
                  />
                </Tooltip>
              )}
            </div>
            <div className="center">
              {infoIndex(indexMessages?.[item?.document_name])}
            </div>
          </Space>
        ),
        delete: (
          <ConfirmModal
            handleConfirm={() => handleDelete(item?.document_id)}
            content="The document will be permanently deleted."
          >
            <Tooltip title="Delete">
              <Button
                size="small"
                className="display-flex-align-center"
                disabled={
                  disableLlmOrDocChange?.length > 0 ||
                  isSinglePassExtractLoading ||
                  indexDocs.includes(item?.document_id) ||
                  isUploading ||
                  isPublicSource
                }
              >
                <DeleteOutlined className="manage-llm-pro-icon" />
              </Button>
            </Tooltip>
          </ConfirmModal>
        ),
        select: (
          <Radio
            checked={selectedDoc?.document_id === item?.document_id}
            onClick={() => handleDocChange(item)}
            disabled={
              disableLlmOrDocChange?.length > 0 ||
              isSinglePassExtractLoading ||
              indexDocs.includes(item?.document_id)
            }
          />
        ),
      };
    });
    setRows(newRows);
  }, [
    listOfDocs,
    selectedDoc,
    disableLlmOrDocChange,
    rawIndexStatus,
    summarizeIndexStatus,
    indexDocs,
    logs,
    isSinglePassExtractLoading,
  ]);

  const beforeUpload = (file) => {
    try {
      setPostHogCustomEvent("ps_uploaded_file", {
        info: "Clicked on '+ Upload New File' button",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

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
      const body = {
        listOfDocs: newListOfDocs,
      };
      updateCustomTool(body);
      handleUpdateTool({ output: doc?.document_id });

      if (
        newListOfDocs?.length === 1 &&
        selectedDoc?.document_id !== doc?.document_id
      ) {
        handleDocChange(doc);
      }
    } else if (info.file.status === "error") {
      setIsUploading(false);
      setAlertDetails({
        type: "error",
        content: "Failed to upload",
      });
    }
  };

  const handleDelete = (docId) => {
    const body = {
      document_id: docId,
    };
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/${details?.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const newListOfDocs = [...listOfDocs].filter(
          (item) => item?.document_id !== docId
        );
        updateCustomTool({ listOfDocs: newListOfDocs });

        if (newListOfDocs?.length === 1 && selectedDoc?.document_id !== docId) {
          const doc = newListOfDocs[1];
          handleDocChange(doc);
        }

        if (docId === selectedDoc?.document_id) {
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
      width={1400}
    >
      <div className="pre-post-amble-body">
        <SpaceWrapper>
          <Space>
            <Typography.Text className="add-cus-tool-header">
              Manage Documents
            </Typography.Text>
          </Space>
          <div>
            <Upload
              name="file"
              action={`/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/${details?.tool_id}`}
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
                    !defaultLlmProfile ||
                    disableLlmOrDocChange?.length > 0 ||
                    isSinglePassExtractLoading ||
                    isPublicSource
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
