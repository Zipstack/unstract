import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  Row,
  Col,
  Button,
  Modal,
  Form,
  Input,
  Empty,
  Spin,
  Typography,
  Space,
  Popconfirm,
} from "antd";
import {
  PlusOutlined,
  FolderOutlined,
  DeleteOutlined,
  CalendarOutlined,
} from "@ant-design/icons";

import {
  projectsApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

function AgenticStudioProjects() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      setLoading(true);
      const data = await projectsApi.list();
      // Handle different response formats
      // DRF paginated: {results: [...], count, next, previous}
      // DRF non-paginated: [...]
      // Custom: {projects: [...]} or {data: [...]}
      const projectsList = Array.isArray(data)
        ? data
        : Array.isArray(data?.results)
        ? data.results
        : Array.isArray(data?.projects)
        ? data.projects
        : Array.isArray(data?.data)
        ? data.data
        : [];
      setProjects(projectsList);
    } catch (error) {
      showApiError(error, "Failed to load projects");
      setProjects([]); // Set empty array on error
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (values) => {
    try {
      setSubmitting(true);
      const project = await projectsApi.create(values);
      showApiSuccess("Project created successfully!");
      setIsModalOpen(false);
      form.resetFields();
      navigate(`projects/${project.id}`);
    } catch (error) {
      showApiError(error, "Failed to create project");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteProject = async (projectId, projectName) => {
    try {
      await projectsApi.delete(projectId);
      showApiSuccess(`Project "${projectName}" deleted successfully`);
      loadProjects();
    } catch (error) {
      showApiError(error, "Failed to delete project");
    }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div style={{ padding: "24px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "24px",
        }}
      >
        <Title level={2} style={{ margin: 0 }}>
          Agentic Studio Projects
        </Title>
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          onClick={() => setIsModalOpen(true)}
        >
          New Project
        </Button>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "60px 0" }}>
          <Spin size="large" />
        </div>
      ) : projects.length === 0 ? (
        <Empty
          description={
            <Space direction="vertical" size="large">
              <Text>No projects yet</Text>
              <Text type="secondary">
                Create your first project to get started
              </Text>
            </Space>
          }
          style={{ marginTop: "60px" }}
        >
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsModalOpen(true)}
          >
            Create Project
          </Button>
        </Empty>
      ) : (
        <Row gutter={[16, 16]}>
          {projects.map((project) => (
            <Col xs={24} sm={12} md={8} lg={6} key={project.id}>
              <Card
                hoverable
                onClick={() => navigate(`projects/${project.id}`)}
                actions={[
                  <Popconfirm
                    title="Delete Project"
                    description={`Are you sure you want to delete "${project.name}"?`}
                    onConfirm={(e) => {
                      e.stopPropagation();
                      handleDeleteProject(project.id, project.name);
                    }}
                    onCancel={(e) => e.stopPropagation()}
                    okText="Yes"
                    cancelText="No"
                    key="delete"
                  >
                    <DeleteOutlined
                      key="delete"
                      onClick={(e) => e.stopPropagation()}
                      style={{ color: "#ff4d4f" }}
                    />
                  </Popconfirm>,
                ]}
                style={{ height: "100%" }}
              >
                <Card.Meta
                  avatar={
                    <FolderOutlined
                      style={{
                        fontSize: "32px",
                        color: "#1890ff",
                      }}
                    />
                  }
                  title={
                    <div
                      style={{
                        fontSize: "16px",
                        fontWeight: 600,
                        marginBottom: "8px",
                      }}
                    >
                      {project.name}
                    </div>
                  }
                  description={
                    <Space
                      direction="vertical"
                      size="small"
                      style={{ width: "100%" }}
                    >
                      {project.description && (
                        <Paragraph
                          ellipsis={{ rows: 2 }}
                          style={{ marginBottom: "8px", color: "#595959" }}
                        >
                          {project.description}
                        </Paragraph>
                      )}
                      <Text type="secondary" style={{ fontSize: "12px" }}>
                        <CalendarOutlined /> {formatDate(project.created_at)}
                      </Text>
                    </Space>
                  }
                />
              </Card>
            </Col>
          ))}
        </Row>
      )}

      <Modal
        title="Create New Project"
        open={isModalOpen}
        onCancel={() => {
          setIsModalOpen(false);
          form.resetFields();
        }}
        footer={null}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreateProject}>
          <Form.Item
            label="Project Name"
            name="name"
            rules={[
              { required: true, message: "Please enter a project name" },
              { min: 3, message: "Project name must be at least 3 characters" },
            ]}
          >
            <Input placeholder="Enter project name" size="large" />
          </Form.Item>

          <Form.Item label="Description (Optional)" name="description">
            <TextArea
              placeholder="Enter project description"
              rows={4}
              showCount
              maxLength={500}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: "24px" }}>
            <Space style={{ float: "right" }}>
              <Button
                onClick={() => {
                  setIsModalOpen(false);
                  form.resetFields();
                }}
              >
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" loading={submitting}>
                Create Project
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default AgenticStudioProjects;
