import { Button, Collapse, Layout, Modal } from "antd";
import {
  FullscreenExitOutlined,
  FullscreenOutlined,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons";
import Sider from "antd/es/layout/Sider";
import { useEffect, useState } from "react";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { Actions } from "../actions/Actions";
import { WorkflowExecution } from "../workflow-execution/WorkflowExecution";
import "./Agency.css";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { useSocketMessagesStore } from "../../../store/socket-messages-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { LogsLabel } from "../logs-label/LogsLabel";
import { SidePanel } from "../side-panel/SidePanel";
import { DisplayLogs } from "../display-logs/DisplayLogs";
import { PageTitle } from "../../widgets/page-title/PageTitle";

function Agency() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [activeKey, setActiveKey] = useState([]);
  const [steps, setSteps] = useState([]);
  const [inputMd, setInputMd] = useState("");
  const [outputMd, setOutputMd] = useState("");
  const [statusBarMsg, setStatusBarMsg] = useState("");
  const [sourceMsg, setSourceMsg] = useState("");
  const [destinationMsg, setDestinationMsg] = useState("");
  const { message, setDefault } = useSocketMessagesStore();
  const { emptyLogs } = useSocketLogsStore();
  const workflowStore = useWorkflowStore();
  const { details, loadingType, projectName } = workflowStore;
  const prompt = details?.prompt_text;
  const [activeToolId, setActiveToolId] = useState("");
  const [prevLoadingType, setPrevLoadingType] = useState("");
  const [isUpdateSteps, setIsUpdateSteps] = useState(false);
  const [stepLoader, setStepLoader] = useState(false);
  const [showLogsModal, setShowLogsModal] = useState(false);

  const openLogsModal = () => {
    setShowLogsModal(true);
  };

  const closeLogsModal = () => {
    setShowLogsModal(false);
  };

  const genExtra = () => (
    <FullscreenOutlined
      onClick={(event) => {
        // If you don't want click extra trigger collapse, you can prevent this:
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
        <div className="agency-ide-logs">
          <DisplayLogs />
        </div>
      ),
      extra: genExtra(),
    },
  ];

  const handleCollapse = (keys) => {
    setActiveKey(keys);
  };

  useEffect(() => {
    if (prevLoadingType !== "EXECUTE") {
      setIsUpdateSteps(true);
    }

    setPrevLoadingType(loadingType);
  }, [workflowStore]);

  useEffect(() => {
    if (!isUpdateSteps) {
      return;
    }
    setToolInstances();
    setIsUpdateSteps(false);
  }, [isUpdateSteps, prompt]);

  const setToolInstances = () => {
    const toolInstances = [...(details?.tool_instances || [])];
    setSteps(toolInstances);
  };

  const initializeWfComp = () => {
    setToolInstances();
    setActiveToolId("");
    setInputMd("");
    setOutputMd("");
    setStatusBarMsg("");
    setDefault();
    emptyLogs();
    setSourceMsg("");
    setDestinationMsg("");
  };

  useEffect(() => {
    // Clean up function to clear all the socket messages
    return () => {
      setDefault();
      emptyLogs();
    };
  }, []);

  useEffect(() => {
    if (Object.keys(message)?.length === 0) {
      return;
    }

    const state = message?.state;
    const msgComp = message?.component;
    if (state === "INPUT_UPDATE") {
      setInputMd(message?.message);
      return;
    }

    if (state === "OUTPUT_UPDATE") {
      setOutputMd(message?.message);
      return;
    }

    if (state === "MESSAGE") {
      setStatusBarMsg(message?.message);
      return;
    }

    if (msgComp === "SOURCE" && state === "RUNNING") {
      setActiveKey("");
      setSourceMsg("");
      setDestinationMsg("");
      const newSteps = [...steps].map((step) => {
        step["progress"] = "";
        step["status"] = "";
        return step;
      });
      setSteps(newSteps);
    }

    if (msgComp === "SOURCE") {
      const srcMsg = message?.state + ": " + message?.message;
      setSourceMsg(srcMsg);
      return;
    }

    if (msgComp === "DESTINATION") {
      const destMsg = message?.state + ": " + message?.message;
      setDestinationMsg(destMsg);
      setActiveToolId("");
      return;
    }

    if (msgComp === "NEXT_STEP") {
      setStepLoader((prev) => !prev);
      return;
    }

    const stepsCopy = [...(steps || [])];
    const newSteps = stepsCopy.map((step) => {
      const stepObj = { ...step };
      if (stepObj?.id !== msgComp) {
        return stepObj;
      }

      setActiveToolId(msgComp);
      stepObj["progress"] = message?.state;
      stepObj["status"] = message?.message;
      return stepObj;
    });
    setSteps(newSteps);
  }, [message]);

  return (
    <div className="agency-layout">
      <PageTitle title={projectName} />
      <Layout className="agency-sider-layout">
        <Layout className="agency-sider-layout">
          <IslandLayout>
            <WorkflowExecution
              setSteps={setSteps}
              activeToolId={activeToolId}
              inputMd={inputMd}
              outputMd={outputMd}
              sourceMsg={sourceMsg}
              destinationMsg={destinationMsg}
            />
          </IslandLayout>
        </Layout>
        <div className="agency-sider-content">
          <div>
            <Sider
              className="agency-sider-layout"
              width={350}
              collapsed={isCollapsed}
              collapsedWidth={30}
            >
              <div className="tool-ide-sider-btn">
                <Button
                  shape="circle"
                  size="small"
                  onClick={() => setIsCollapsed(!isCollapsed)}
                  icon={isCollapsed ? <LeftOutlined /> : <RightOutlined />}
                />
              </div>
              {!isCollapsed && <SidePanel />}
            </Sider>
          </div>
        </div>
      </Layout>
      <div className="agency-actions">
        <Actions
          statusBarMsg={statusBarMsg}
          initializeWfComp={initializeWfComp}
          stepLoader={stepLoader}
        />
      </div>
      <div className="agency-footer">
        <Collapse
          className="agency-ide-collapse-panel"
          size="small"
          activeKey={activeKey}
          items={getItems()}
          expandIconPosition="end"
          onChange={handleCollapse}
          bordered={false}
        />
        <Modal
          title="Logs"
          open={showLogsModal}
          onCancel={closeLogsModal}
          className="agency-ide-log-modal"
          footer={null}
          width={1000}
          closeIcon={<FullscreenExitOutlined />}
        >
          <LogsLabel />
          <div className="agency-ide-logs">
            <DisplayLogs />
          </div>
        </Modal>
      </div>
    </div>
  );
}

export { Agency };
