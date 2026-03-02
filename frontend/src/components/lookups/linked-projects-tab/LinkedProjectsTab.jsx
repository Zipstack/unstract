import {
  DisconnectOutlined,
  FolderOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  Button,
  Form,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import "./LinkedProjectsTab.css";

const { Title, Text } = Typography;
const { Option } = Select;

export function LinkedProjectsTab({ project }) {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [availableProjects, setAvailableProjects] = useState([]);
  const [psProjectsMap, setPsProjectsMap] = useState({});
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [form] = Form.useForm();

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    fetchLinks();
    fetchPSProjects(); // Fetch PS projects to build name mapping
  }, [project.id]);

  const fetchPSProjects = async () => {
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`
      );
      const projects = response.data.results || response.data || [];
      // Build a map of PS project tool_id -> tool name
      // The prompt_studio_project_id in links is the tool_id (UUID)
      const projectsMap = {};
      projects.forEach((proj) => {
        projectsMap[proj.tool_id] = proj.tool_name || "Unnamed Project";
      });
      setPsProjectsMap(projectsMap);
    } catch (error) {
      console.error("Failed to fetch PS projects for name mapping:", error);
    }
  };

  const fetchLinks = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-links/`,
        {
          params: { lookup_project_id: project.id },
        }
      );
      setLinks(response.data.results || []);
    } catch (error) {
      console.error("Failed to fetch linked projects:", error);
      setAlertDetails({
        type: "error",
        content:
          error.response?.data?.detail || "Failed to fetch linked projects",
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchAvailableProjects = async () => {
    setLoadingProjects(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`
      );
      const projects = response.data.results || response.data || [];
      console.log("Fetched available projects:", projects);
      console.log("Number of projects fetched:", projects.length);

      // Filter out already linked projects
      const linkedProjectIds = links.map(
        (link) => link.prompt_studio_project_id
      );
      console.log("Already linked project IDs:", linkedProjectIds);

      const unlinkedProjects = projects.filter(
        (p) => !linkedProjectIds.includes(p.tool_id)
      );
      console.log(
        "Unlinked projects after filter:",
        unlinkedProjects.map((p) => ({ tool_id: p.tool_id, id: p.id }))
      );
      console.log("Unlinked projects:", unlinkedProjects);
      console.log("Number of unlinked projects:", unlinkedProjects.length);
      console.log("Projects for selection:", projects);

      setAvailableProjects(unlinkedProjects);

      // Check for duplicate IDs
      console.log(
        "Raw projects before filter:",
        projects.map((p) => ({ tool_id: p.tool_id, id: p.id }))
      );
      const ids = unlinkedProjects.map((p) => p.tool_id);
      const uniqueIds = new Set(ids);
      if (ids.length !== uniqueIds.size) {
        console.warn("Warning: Duplicate project IDs detected!", ids);
      }

      console.log(
        "Available projects for selection:",
        unlinkedProjects.map((p) => ({ id: p.tool_id, name: p.tool_name }))
      );

      if (unlinkedProjects.length === 0 && projects.length > 0) {
        setAlertDetails({
          type: "info",
          content: "All Prompt Studio projects are already linked",
        });
      }
    } catch (error) {
      console.error("Failed to fetch Prompt Studio projects:", error);
      setAlertDetails({
        type: "error",
        content: "Failed to fetch available Prompt Studio projects",
      });
    } finally {
      setLoadingProjects(false);
    }
  };

  const handleLink = async () => {
    try {
      console.log("handleLink called");
      console.log("Current form field values:", form.getFieldsValue());

      const values = await form.validateFields();
      console.log("Validated form values:", values);
      const selectedProject = values.prompt_studio_project;
      console.log("Selected project ID:", selectedProject);

      if (!selectedProject) {
        console.error("No project selected!");
        setAlertDetails({
          type: "error",
          content: "Please select a project to link",
        });
        return;
      }

      await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-links/`,
        {
          prompt_studio_project_id: selectedProject,
          lookup_project: project.id,
        },
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        }
      );

      setAlertDetails({
        type: "success",
        content: "Project linked successfully",
      });
      setLinkModalOpen(false);
      form.resetFields();
      fetchLinks();
    } catch (error) {
      console.error("Link error:", error);
      if (error.errorFields) {
        // Form validation error
        console.log("Validation errors:", error.errorFields);
        return;
      }
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to link project",
      });
    }
  };

  const handleUnlink = async (linkId) => {
    Modal.confirm({
      title: "Unlink Project",
      content: "Are you sure you want to unlink this Prompt Studio project?",
      okText: "Unlink",
      okType: "danger",
      onOk: async () => {
        try {
          await axiosPrivate.delete(
            `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-links/${linkId}/`,
            {
              headers: {
                "X-CSRFToken": sessionDetails?.csrfToken,
              },
            }
          );
          setAlertDetails({
            type: "success",
            content: "Project unlinked successfully",
          });
          fetchLinks();
        } catch (error) {
          console.error("Failed to unlink project:", error);
          setAlertDetails({
            type: "error",
            content: error.response?.data?.detail || "Failed to unlink project",
          });
        }
      },
    });
  };

  const columns = [
    {
      title: "Prompt Studio Project",
      key: "project",
      render: (_, record) => (
        <Space>
          <FolderOutlined />
          <Text strong>
            {psProjectsMap[record.prompt_studio_project_id] ||
              `Project ${record.prompt_studio_project_id.substring(0, 8)}...`}
          </Text>
        </Space>
      ),
    },
    {
      title: "Linked Date",
      dataIndex: "created_at",
      key: "created_at",
      render: (date) => new Date(date).toLocaleDateString(),
    },
    {
      title: "Status",
      key: "status",
      render: () => <Tag color="green">Active</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Button
          icon={<DisconnectOutlined />}
          danger
          size="small"
          onClick={() => handleUnlink(record.id)}
        >
          Unlink
        </Button>
      ),
    },
  ];

  return (
    <div className="linked-projects-tab">
      <div className="tab-header">
        <div>
          <Title level={4}>Linked Prompt Studio Projects</Title>
          <Text type="secondary">
            Prompt Studio projects that can use this Look-Up for enrichment
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={async () => {
            setLinkModalOpen(true);
            await fetchAvailableProjects();
          }}
        >
          Link Project
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={links}
        loading={loading}
        rowKey="id"
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
        }}
        locale={{
          emptyText: "No linked projects. Click 'Link Project' to get started.",
        }}
      />

      <Modal
        title="Link Prompt Studio Project"
        open={linkModalOpen}
        onCancel={() => {
          setLinkModalOpen(false);
          form.resetFields();
          setAvailableProjects([]);
        }}
        onOk={handleLink}
        okText="Link"
        confirmLoading={loading}
        centered
        maskClosable={false}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="prompt_studio_project"
            label="Select a Prompt Studio project to link with this Look-Up:"
            rules={[
              { required: true, message: "Please select a project to link" },
            ]}
          >
            <Select
              placeholder="Select a Prompt Studio project"
              loading={loadingProjects}
              showSearch
              optionFilterProp="children"
              notFoundContent={
                loadingProjects ? "Loading..." : "No available projects"
              }
              onSelect={(value) => {
                console.log("onSelect fired - value:", value);
                const selected = availableProjects.find(
                  (p) => p.tool_id === value
                );
                console.log("Selected project:", selected);
              }}
              onDropdownVisibleChange={(open) => {
                console.log("Dropdown visible:", open);
                if (open) {
                  console.log(
                    "Available projects count:",
                    availableProjects.length
                  );
                  console.log("Projects:", availableProjects);
                }
              }}
            >
              {availableProjects.map((p) => (
                <Option key={p.tool_id} value={p.tool_id}>
                  {p.tool_name || "Unnamed Project"}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Text type="secondary">
            Linked projects will be able to use this Look-Up for data enrichment
            during prompt execution.
          </Text>
        </Form>
      </Modal>
    </div>
  );
}

LinkedProjectsTab.propTypes = {
  project: PropTypes.shape({
    id: PropTypes.string.isRequired,
  }).isRequired,
};
