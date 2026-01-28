import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Card,
  Tabs,
  Typography,
  Button,
  Space,
  Spin,
  Tag,
  Modal,
  Form,
  Input,
  Popconfirm,
} from "antd";
import {
  ArrowLeftOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ReferenceDataTab } from "../reference-data-tab/ReferenceDataTab";
import { TemplateTab } from "../template-tab/TemplateTab";
import { ProfileManagementTab } from "../profile-management-tab/ProfileManagementTab";
import { LinkedProjectsTab } from "../linked-projects-tab/LinkedProjectsTab";
import { ExecutionHistoryTab } from "../execution-history-tab/ExecutionHistoryTab";
import { DebugTab } from "../debug-tab/DebugTab";
import "./LookUpProjectDetail.css";

const { Title } = Typography;
const { TextArea } = Input;

export function LookUpProjectDetail() {
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("reference");
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [form] = Form.useForm();
  const { projectId } = useParams();
  const navigate = useNavigate();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    fetchProject();
  }, [projectId]);

  const fetchProject = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${projectId}/`
      );
      setProject(response.data);
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: "Failed to fetch project details",
      });
      navigate("../");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenEditModal = () => {
    form.setFieldsValue({
      name: project.name,
      description: project.description || "",
    });
    setEditModalOpen(true);
  };

  const handleEditProject = async () => {
    try {
      const values = await form.validateFields();
      setEditLoading(true);

      // Get CSRF token from cookie as fallback
      const csrfToken =
        sessionDetails?.csrfToken ||
        document.cookie
          .split("; ")
          .find((row) => row.startsWith("csrftoken="))
          ?.split("=")[1];

      await axiosPrivate.patch(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${projectId}/`,
        values,
        {
          headers: {
            "X-CSRFToken": csrfToken,
            "Content-Type": "application/json",
          },
        }
      );

      setAlertDetails({
        type: "success",
        content: "Project updated successfully",
      });
      setEditModalOpen(false);
      fetchProject();
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to update project",
      });
    } finally {
      setEditLoading(false);
    }
  };

  const handleDeleteProject = async () => {
    try {
      setDeleteLoading(true);

      // Get CSRF token from cookie as fallback
      const csrfToken =
        sessionDetails?.csrfToken ||
        document.cookie
          .split("; ")
          .find((row) => row.startsWith("csrftoken="))
          ?.split("=")[1];

      await axiosPrivate.delete(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${projectId}/`,
        {
          headers: {
            "X-CSRFToken": csrfToken,
          },
        }
      );

      setAlertDetails({
        type: "success",
        content: "Project deleted successfully",
      });
      navigate("../");
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to delete project",
      });
    } finally {
      setDeleteLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-container">
        <Spin size="large" />
      </div>
    );
  }

  if (!project) {
    return null;
  }

  const tabItems = [
    {
      key: "reference",
      label: "Reference Data",
      children: <ReferenceDataTab project={project} onUpdate={fetchProject} />,
    },
    {
      key: "template",
      label: "Template",
      children: <TemplateTab project={project} onUpdate={fetchProject} />,
    },
    {
      key: "debug",
      label: "Debug",
      children: <DebugTab project={project} />,
    },
    {
      key: "profiles",
      label: "Profiles",
      children: <ProfileManagementTab projectId={projectId} />,
    },
    {
      key: "linked",
      label: "Linked Projects",
      children: <LinkedProjectsTab project={project} />,
    },
    {
      key: "history",
      label: "Execution History",
      children: <ExecutionHistoryTab project={project} />,
    },
  ];

  return (
    <div className="lookup-project-detail">
      <div className="project-header">
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("../")}>
            Back
          </Button>
        </Space>

        <div className="project-info">
          <div>
            <Title level={3}>{project.name}</Title>
          </div>
          <Space>
            <Tag color={project.is_active ? "green" : "orange"}>
              {project.is_active ? "Active" : "Inactive"}
            </Tag>
            <Button icon={<EditOutlined />} onClick={handleOpenEditModal}>
              Edit
            </Button>
            <Popconfirm
              title="Delete Project"
              description="Are you sure you want to delete this project? This action cannot be undone."
              onConfirm={handleDeleteProject}
              okText="Delete"
              cancelText="Cancel"
              okButtonProps={{ danger: true, loading: deleteLoading }}
            >
              <Button icon={<DeleteOutlined />} danger loading={deleteLoading}>
                Delete
              </Button>
            </Popconfirm>
          </Space>
        </div>
      </div>

      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          size="large"
        />
      </Card>

      {/* Edit Project Modal */}
      <Modal
        title="Edit Project"
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        onOk={handleEditProject}
        okText="Save"
        confirmLoading={editLoading}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="Project Name"
            rules={[
              { required: true, message: "Please enter a project name" },
              { max: 100, message: "Name must be less than 100 characters" },
            ]}
          >
            <Input placeholder="e.g., Vendor Enrichment" />
          </Form.Item>

          <Form.Item
            name="description"
            label="Description"
            rules={[
              {
                max: 500,
                message: "Description must be less than 500 characters",
              },
            ]}
          >
            <TextArea
              rows={3}
              placeholder="Describe the purpose of this Look-Up project..."
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
