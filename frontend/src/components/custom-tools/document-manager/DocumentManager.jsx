import { Button, Space, Tabs, Tooltip, Typography } from "antd";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";
import "@react-pdf-viewer/page-navigation/lib/styles/index.css";
import PropTypes from "prop-types";

import "./DocumentManager.css";
import { LeftOutlined, RightOutlined } from "@ant-design/icons";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { PdfViewer } from "../pdf-viewer/PdfViewer";
import { ManageDocsModal } from "../manage-docs-modal/ManageDocsModal";
import { useEffect, useState } from "react";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import {
  base64toBlob,
  removeFileExtension,
} from "../../../helpers/GetStaticData";
import { DocumentViewer } from "../document-viewer/DocumentViewer";
import { TextViewer } from "../text-viewer/TextViewer";

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
  pdf: "PDF",
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
      key: 3,
      label: tabLabel,
    });
  }
} catch (err) {
  console.log(err);
}

function DocumentManager({ generateIndex, handleUpdateTool, handleDocChange }) {
  const [openManageDocsModal, setOpenManageDocsModal] = useState(false);
  const [page, setPage] = useState(1);
  const [activeKey, setActiveKey] = useState("1");
  const [fileUrl, setFileUrl] = useState("");
  const [extractTxt, setExtractTxt] = useState("");
  const [isDocLoading, setIsDocLoading] = useState(false);
  const [isExtractLoading, setIsExtractLoading] = useState(false);
  const { selectedDoc, listOfDocs, disableLlmOrDocChange, details } =
    useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    const fileNameTxt = removeFileExtension(selectedDoc);
    const files = [
      {
        fileName: selectedDoc,
        viewType: viewTypes.pdf,
      },
      {
        fileName: `extract/${fileNameTxt}.txt`,
        viewType: viewTypes.extract,
      },
    ];

    setFileUrl("");
    setExtractTxt("");
    files.forEach((item) => {
      handleFetchContent(item);
    });
  }, [selectedDoc]);

  const handleFetchContent = (fileDetails) => {
    if (!selectedDoc) {
      setFileUrl("");
      setExtractTxt("");
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/fetch_contents?file_name=${fileDetails?.fileName}&tool_id=${details?.tool_id}`,
    };

    handleLoadingStateUpdate(fileDetails?.viewType, true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data?.data;
        if (fileDetails?.viewType === viewTypes.pdf) {
          const base64String = data || "";
          const blob = base64toBlob(base64String);
          setFileUrl(URL.createObjectURL(blob));
          return;
        }

        if (fileDetails?.viewType === viewTypes?.extract) {
          setExtractTxt(data);
        }
      })
      .catch((err) => {})
      .finally(() => {
        handleLoadingStateUpdate(fileDetails?.viewType, false);
      });
  };

  const handleLoadingStateUpdate = (viewType, value) => {
    if (viewType === viewTypes.pdf) {
      setIsDocLoading(value);
    }

    if (viewType === viewTypes.extract) {
      setIsExtractLoading(value);
    }
  };

  const handleActiveKeyChange = (key) => {
    setActiveKey(key);
  };

  useEffect(() => {
    const index = [...listOfDocs].findIndex((item) => item === selectedDoc);
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
    handleDocChange(newSelectedDoc);
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
            <Tooltip title="Manage Documents">
              <Button
                className="doc-manager-btn"
                onClick={() => setOpenManageDocsModal(true)}
              >
                <Typography.Text ellipsis>
                  {selectedDoc || "No Document Selected"}
                </Typography.Text>
              </Button>
            </Tooltip>
          </div>
          <div>
            <Button
              type="text"
              size="small"
              disabled={
                !selectedDoc || disableLlmOrDocChange?.length > 0 || page <= 1
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
          doc={selectedDoc}
          isLoading={isDocLoading}
          isContentAvailable={fileUrl?.length > 0}
          setOpenManageDocsModal={setOpenManageDocsModal}
        >
          <PdfViewer fileUrl={fileUrl} />
        </DocumentViewer>
      )}
      {activeKey === "2" && (
        <DocumentViewer
          doc={selectedDoc}
          isLoading={isExtractLoading}
          isContentAvailable={extractTxt?.length > 0}
          setOpenManageDocsModal={setOpenManageDocsModal}
        >
          <TextViewer text={extractTxt} />
        </DocumentViewer>
      )}
      {SummarizeView && activeKey === 3 && (
        <SummarizeView setOpenManageDocsModal={setOpenManageDocsModal} />
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
