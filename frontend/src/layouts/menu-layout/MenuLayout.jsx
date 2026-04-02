import { QuestionCircleOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Space } from "antd";
import PropTypes from "prop-types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ToolNavBar } from "../../components/navigations/tool-nav-bar/ToolNavBar";
import { workflowService } from "../../components/workflows/workflow/workflow-service";
import { useExceptionHandler } from "../../hooks/useExceptionHandler";
import { useAlertStore } from "../../store/alert-store";
import { useSessionStore } from "../../store/session-store";
import { useWorkflowStore } from "../../store/workflow-store";
import "./MenuLayout.css";

function MenuLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const currentMenu = useRef();
  const [activeTab, setActiveTab] = useState("");
  const { sessionDetails } = useSessionStore();
  const { projectName, projectId, details } = useWorkflowStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const wfService = workflowService();

  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editForm] = Form.useForm();

  useEffect(() => {
    currentMenu.current = location.pathname;
    const pathnameSplit = currentMenu.current.split("/");
    const lastIndex = pathnameSplit.length - 1;
    if (lastIndex === -1) {
      return;
    }

    const value = pathnameSplit[lastIndex];
    setActiveTab(value);
  }, []);

  const handleNavigateBack = useCallback(() => {
    if (location.state?.from) {
      const from = location.state.from;
      const fromState =
        typeof from === "object" && from.state ? from.state : {};
      const mergedState = {
        ...fromState,
        ...(location.state?.scrollToCardId && {
          scrollToCardId: location.state.scrollToCardId,
        }),
      };
      const nextState = Object.keys(mergedState).length
        ? mergedState
        : undefined;
      if (typeof from === "object") {
        navigate({ ...from, state: nextState });
      } else {
        navigate(from, { state: nextState });
      }
    } else if (sessionDetails?.orgName) {
      navigate(`/${sessionDetails.orgName}/workflows`);
    }
  }, [location.state, sessionDetails.orgName, navigate]);

  const handleOpenEditModal = useCallback(() => {
    editForm.setFieldsValue({
      workflow_name: projectName || "",
      description: details?.description || "",
    });
    setEditModalOpen(true);
  }, [projectName, details, editForm]);

  const handleEditSubmit = useCallback(async () => {
    try {
      const values = await editForm.validateFields();
      await wfService.editProject(
        values.workflow_name,
        values.description,
        projectId,
      );
      // Use Zustand's setState directly for correct shallow merge
      useWorkflowStore.setState({
        projectName: values.workflow_name,
        details: { ...details, description: values.description },
      });
      setEditModalOpen(false);
      setAlertDetails({ type: "success", content: "Updated successfully" });
    } catch (err) {
      if (err?.errorFields) {
        return;
      }
      setAlertDetails(handleException(err, "Failed to update workflow"));
    }
  }, [editForm, projectId, details, setAlertDetails, handleException]);

  const rightButtons = useMemo(
    () => (
      <Space>
        <Button
          key="help"
          icon={<QuestionCircleOutlined />}
          disabled={true}
          type={activeTab === "help" ? "primary" : "default"}
        >
          Help
        </Button>
      </Space>
    ),
    [activeTab],
  );

  return (
    <>
      <ToolNavBar
        title={projectName || "Name of the project"}
        subtitle={details?.description}
        onNavigateBack={handleNavigateBack}
        onEditTitle={projectId ? handleOpenEditModal : undefined}
        customButtons={rightButtons}
      />
      <Modal
        title="Edit Workflow"
        open={editModalOpen}
        onOk={handleEditSubmit}
        okButtonProps={{ disabled: !projectId }}
        onCancel={() => setEditModalOpen(false)}
        okText="Save"
        centered
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="workflow_name"
            label="Workflow Name"
            rules={[{ required: true, message: "Name is required" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
      <div className="appBody">
        <div className="appBody2">{children}</div>
      </div>
    </>
  );
}

MenuLayout.propTypes = {
  children: PropTypes.oneOfType([PropTypes.node, PropTypes.element]),
};

export { MenuLayout };
