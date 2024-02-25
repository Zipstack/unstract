import { Button, Typography } from "antd";
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

function DocumentManager({ generateIndex, handleUpdateTool, handleDocChange }) {
  const [openManageDocsModal, setOpenManageDocsModal] = useState(false);
  const [page, setPage] = useState(1);
  const { selectedDoc, listOfDocs, disableLlmOrDocChange } =
    useCustomToolStore();

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
        <div>
          <Button
            className="doc-manager-btn"
            onClick={() => setOpenManageDocsModal(true)}
          >
            <Typography.Text ellipsis>
              {selectedDoc || "No Document Selected"}
            </Typography.Text>
          </Button>
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
      </div>
      <PdfViewer setOpenManageDocsModal={setOpenManageDocsModal} />
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
