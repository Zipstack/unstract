import { LeftOutlined, RightOutlined } from "@ant-design/icons";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";
import "@react-pdf-viewer/page-navigation/lib/styles/index.css";
import { Button, Space, Tabs, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import "./DocumentManager.css";

import { base64toBlob, docIndexStatus } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { DocumentViewer } from "../document-viewer/DocumentViewer";
import { ManageDocsModal } from "../manage-docs-modal/ManageDocsModal";
import { PdfViewer } from "../pdf-viewer/PdfViewer";
import { TextViewerPre } from "../text-viewer-pre/TextViewerPre";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

const items = [
  {
    key: "1",
    label: "Doc View",
  },
  {
    key: "2",
    label: "Raw View",
  },
];

const viewTypes = {
  original: "ORIGINAL",
  extract: "EXTRACT",
};

let SummarizeView = null;
try {
  SummarizeView =
    require("../../../plugins/summarize-view/SummarizeView").SummarizeView;
  const tabLabel =
    require("../../../plugins/summarize-tab/SummarizeTab").tabLabel;
  if (tabLabel) {
    items.push({
      key: "3",
      label: tabLabel,
    });
  }
} catch {
  // The component will remain null of it is not available
}

function DocumentManager({ generateIndex, handleUpdateTool, handleDocChange }) {
  const [openManageDocsModal, setOpenManageDocsModal] = useState(false);
  const [page, setPage] = useState(1);
  const [activeKey, setActiveKey] = useState("1");
  const [fileUrl, setFileUrl] = useState("");
  const [fileErrMsg, setFileErrMsg] = useState("");
  const [extractTxt, setExtractTxt] = useState("");
  const [extractErrMsg, setExtractErrMsg] = useState("");
  const [isDocLoading, setIsDocLoading] = useState(false);
  const [isExtractLoading, setIsExtractLoading] = useState(false);
  const [currDocIndexStatus, setCurrDocIndexStatus] = useState(
    docIndexStatus.yet_to_start
  );
  const {
    selectedDoc,
    listOfDocs,
    disableLlmOrDocChange,
    details,
    indexDocs,
    isSinglePassExtractLoading,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    setFileUrl("");
    setExtractTxt("");
    Object.keys(viewTypes).forEach((item) => {
      handleFetchContent(viewTypes[item]);
    });
  }, [selectedDoc]);

  useEffect(() => {
    if (currDocIndexStatus === docIndexStatus.done) {
      handleFetchContent(viewTypes.extract);
      setCurrDocIndexStatus(docIndexStatus.yet_to_start);
    }
  }, [currDocIndexStatus]);

  useEffect(() => {
    if (docIndexStatus.yet_to_start === currDocIndexStatus) {
      const isIndexing = indexDocs.find(
        (item) => item === selectedDoc?.document_id
      );

      if (isIndexing) {
        setCurrDocIndexStatus(docIndexStatus.indexing);
      }
      return;
    }

    if (docIndexStatus.indexing === currDocIndexStatus) {
      const isIndexing = indexDocs.find(
        (item) => item === selectedDoc?.document_id
      );

      if (!isIndexing) {
        setCurrDocIndexStatus(docIndexStatus.done);
      }
    }
  }, [indexDocs]);

  const handleFetchContent = (viewType) => {
    if (viewType === viewTypes.original) {
      setFileUrl("");
      setFileErrMsg("");
    }

    if (viewType === viewTypes.extract) {
      setExtractTxt("");
      setExtractErrMsg("");
    }

    if (!selectedDoc?.document_id) {
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/${details?.tool_id}?document_id=${selectedDoc?.document_id}&view_type=${viewType}`,
    };

    handleLoadingStateUpdate(viewType, true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data?.data;
        if (viewType === viewTypes.original) {
          const base64String = data || "";
          const blob = base64toBlob(base64String);
          setFileUrl(URL.createObjectURL(blob));
          return;
        }

        if (viewType === viewTypes?.extract) {
          setExtractTxt(data);
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to fetch"));
        if (err?.response?.status === 404) {
          setErrorMessage(viewType);
        }
      })
      .finally(() => {
        handleLoadingStateUpdate(viewType, false);
      });
  };

  const handleLoadingStateUpdate = (viewType, value) => {
    if (viewType === viewTypes.original) {
      setIsDocLoading(value);
    }

    if (viewType === viewTypes.extract) {
      setIsExtractLoading(value);
    }
  };

  const handleActiveKeyChange = (key) => {
    setActiveKey(key);
  };

  const setErrorMessage = (viewType) => {
    if (viewType === viewTypes.original) {
      setFileErrMsg("Document not found.");
    }

    if (viewType === viewTypes.extract) {
      setExtractErrMsg(
        "Raw content is not available. Please index or re-index to generate it."
      );
    }
  };

  useEffect(() => {
    const index = [...listOfDocs].findIndex(
      (item) => item?.document_id === selectedDoc?.document_id
    );
    setPage(index + 1);
  }, [selectedDoc, listOfDocs]);

  const handlePageLeft = () => {
    if (page <= 1) {
      return;
    }

    const newPage = page - 1;
    updatePageAndDoc(newPage);
  };

  const handlePageRight = () => {
    if (page >= listOfDocs?.length) {
      return;
    }

    const newPage = page + 1;
    updatePageAndDoc(newPage);
  };

  const updatePageAndDoc = (newPage) => {
    setPage(newPage);
    const newSelectedDoc = listOfDocs[newPage - 1];
    handleDocChange(newSelectedDoc?.document_id);
  };

  return (
    <div className="doc-manager-layout">
      <div className="doc-manager-header">
        <div className="tools-main-tabs">
          <Tabs
            activeKey={activeKey}
            items={items}
            onChange={handleActiveKeyChange}
          />
        </div>
        <Space>
          <div>
            {selectedDoc ? (
              <Typography.Text className="doc-main-title" ellipsis>
                {selectedDoc?.document_name}
              </Typography.Text>
            ) : null}
          </div>
          <div>
            <Tooltip title="Manage Documents">
              <Button
                className="doc-manager-btn"
                onClick={() => setOpenManageDocsModal(true)}
              >
                <Typography.Text ellipsis>{"Manage Documents"}</Typography.Text>
              </Button>
            </Tooltip>
          </div>
          <div>
            <Button
              type="text"
              size="small"
              disabled={
                !selectedDoc ||
                disableLlmOrDocChange?.length > 0 ||
                isSinglePassExtractLoading ||
                page <= 1
              }
              onClick={handlePageLeft}
            >
              <LeftOutlined className="doc-manager-paginate-icon" />
            </Button>
            <Button
              type="text"
              size="small"
              disabled={
                !selectedDoc ||
                disableLlmOrDocChange?.length > 0 ||
                isSinglePassExtractLoading ||
                page >= listOfDocs?.length
              }
              onClick={handlePageRight}
            >
              <RightOutlined className="doc-manager-paginate-icon" />
            </Button>
          </div>
        </Space>
      </div>
      {activeKey === "1" && (
        <DocumentViewer
          doc={selectedDoc?.document_name}
          isLoading={isDocLoading}
          isContentAvailable={fileUrl?.length > 0}
          setOpenManageDocsModal={setOpenManageDocsModal}
          errMsg={fileErrMsg}
        >
          <PdfViewer fileUrl={fileUrl} />
        </DocumentViewer>
      )}
      {activeKey === "2" && (
        <DocumentViewer
          doc={selectedDoc?.document_name}
          isLoading={isExtractLoading}
          isContentAvailable={extractTxt?.length > 0}
          setOpenManageDocsModal={setOpenManageDocsModal}
          errMsg={extractErrMsg}
        >
          <TextViewerPre text={extractTxt} />
        </DocumentViewer>
      )}
      {SummarizeView && activeKey === "3" && (
        <SummarizeView
          setOpenManageDocsModal={setOpenManageDocsModal}
          currDocIndexStatus={currDocIndexStatus}
        />
      )}
      <ManageDocsModal
        open={openManageDocsModal}
        setOpen={setOpenManageDocsModal}
        generateIndex={generateIndex}
        handleUpdateTool={handleUpdateTool}
        handleDocChange={handleDocChange}
      />
    </div>
  );
}

DocumentManager.propTypes = {
  generateIndex: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
  handleDocChange: PropTypes.func.isRequired,
};

export { DocumentManager };
