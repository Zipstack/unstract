import { FullscreenExitOutlined, FullscreenOutlined } from "@ant-design/icons";
import { Col, Collapse, Modal, Row } from "antd";
import { useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomSynonymsModal } from "../custom-synonyms-modal/CustomSynonymsModal";
import { DisplayLogs } from "../display-logs/DisplayLogs";
import { DocumentManager } from "../document-manager/DocumentManager";
import { Header } from "../header/Header";
import { LogsLabel } from "../logs-label/LogsLabel";
import { SettingsModal } from "../settings-modal/SettingsModal";
import { ToolsMain } from "../tools-main/ToolsMain";
import "./ToolIde.css";

function ToolIde() {
  const [showLogsModal, setShowLogsModal] = useState(false);
  const [activeKey, setActiveKey] = useState([]);
  const [openCusSynonymsModal, setOpenCusSynonymsModal] = useState(false);
  const [openSettings, setOpenSettings] = useState(false);
  const {
    details,
    updateCustomTool,
    disableLlmOrDocChange,
    selectedDoc,
    indexDocs,
    pushIndexDoc,
    deleteIndexDoc,
  } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const openLogsModal = () => {
    setShowLogsModal(true);
  };

  const closeLogsModal = () => {
    setShowLogsModal(false);
  };

  const genExtra = () => (
    <FullscreenOutlined
      onClick={(event) => {
        openLogsModal();
        event.stopPropagation();
      }}
    />
  );

  const getItems = () => [
    {
      key: "1",
      label: activeKey?.length > 0 ? <LogsLabel /> : "Logs",
      children: (
        <div className="tool-ide-logs">
          <DisplayLogs />
        </div>
      ),
      extra: genExtra(),
    },
  ];

  const handleCollapse = (keys) => {
    setActiveKey(keys);
  };

  const generateIndex = async (doc) => {
    const docId = doc?.document_id;

    if (indexDocs.includes(docId)) {
      setAlertDetails({
        type: "error",
        content: "This document is already getting indexed",
      });
      return;
    }

    const body = {
      document_id: docId,
    };

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/index-document/${details?.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    pushIndexDoc(docId);
    return axiosPrivate(requestOptions)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: `${doc?.document_name} - Indexed successfully`,
        });
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, `${doc?.document_name} - Failed to index`)
        );
      })
      .finally(() => {
        deleteIndexDoc(docId);
      });
  };

  const handleUpdateTool = async (body) => {
    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${details?.tool_id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    return axiosPrivate(requestOptions)
      .then((res) => {
        return res;
      })
      .catch((err) => {
        throw err;
      });
  };

  const handleDocChange = (doc) => {
    if (disableLlmOrDocChange?.length > 0) {
      setAlertDetails({
        type: "error",
        content: "Please wait for the run to complete",
      });
      return;
    }

    const prevSelectedDoc = selectedDoc;
    const data = {
      selectedDoc: doc,
    };
    updateCustomTool(data);

    const body = {
      output: doc?.document_id,
    };

    handleUpdateTool(body).catch((err) => {
      const revertSelectedDoc = {
        selectedDoc: prevSelectedDoc,
      };
      updateCustomTool(revertSelectedDoc);
      setAlertDetails(handleException(err, "Failed to select the document"));
    });
  };

  return (
    <div className="tool-ide-layout">
      <div>
        <Header
          handleUpdateTool={handleUpdateTool}
          setOpenSettings={setOpenSettings}
        />
      </div>
      <div className="tool-ide-body">
        <div className="tool-ide-body-2">
          <Row className="tool-ide-main">
            <Col span={12} className="tool-ide-col">
              <div className="tool-ide-prompts">
                <ToolsMain />
              </div>
            </Col>
            <Col span={12} className="tool-ide-col">
              <div className="tool-ide-pdf">
                <DocumentManager
                  generateIndex={generateIndex}
                  handleUpdateTool={handleUpdateTool}
                  handleDocChange={handleDocChange}
                />
              </div>
            </Col>
          </Row>
          <div className="tool-ide-footer">
            <Collapse
              className="tool-ide-collapse-panel"
              size="small"
              activeKey={activeKey}
              items={getItems()}
              expandIconPosition="end"
              onChange={handleCollapse}
            />
          </div>
          <Modal
            title={<LogsLabel />}
            open={showLogsModal}
            onCancel={closeLogsModal}
            className="agency-ide-log-modal"
            footer={null}
            width={1400}
            closeIcon={<FullscreenExitOutlined />}
          >
            <div className="agency-ide-logs">
              <DisplayLogs />
            </div>
          </Modal>
        </div>
      </div>
      <CustomSynonymsModal
        open={openCusSynonymsModal}
        setOpen={setOpenCusSynonymsModal}
      />
      <SettingsModal
        open={openSettings}
        setOpen={setOpenSettings}
        handleUpdateTool={handleUpdateTool}
      />
    </div>
  );
}

export { ToolIde };
