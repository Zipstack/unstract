import {
  Button,
  Card,
  Input,
  Space,
  Table,
  Tag,
  Typography,
  Popconfirm,
} from "antd";
import {
  PlusOutlined,
  SearchOutlined,
  FileTextOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { CreateProjectModal } from "../create-project-modal/CreateProjectModal";
import "./LookUpProjectList.css";

const { Title, Text } = Typography;
const { Search } = Input;

export function LookUpProjectList() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);

  const navigate = useNavigate();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    if (sessionDetails?.orgId) {
      fetchProjects();
    }
  }, [sessionDetails?.orgId]);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/`
      );
      setProjects(response.data.results || response.data || []);
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: "Failed to fetch Look-Up projects",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (values) => {
    try {
      const response = await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/`,
        values,
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        }
      );
      setAlertDetails({
        type: "success",
        content: "Look-Up project created successfully",
      });
      setCreateModalOpen(false);
      fetchProjects();
      navigate(response.data.id);
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to create project",
      });
    }
  };

  const handleDeleteProject = async (projectId) => {
    try {
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
      fetchProjects();
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: error.response?.data?.detail || "Failed to delete project",
      });
    }
  };

  const filteredProjects = projects.filter(
    (project) =>
      project.name.toLowerCase().includes(searchText.toLowerCase()) ||
      project.description?.toLowerCase().includes(searchText.toLowerCase())
  );

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (text, record) => (
        <Button
          type="link"
          onClick={() => navigate(record.id)}
          style={{ padding: 0 }}
        >
          {text}
        </Button>
      ),
    },
    {
      title: "Type",
      dataIndex: "reference_data_type",
      key: "reference_data_type",
      render: (type) => (
        <Tag color="blue">{type?.replace(/_/g, " ").toUpperCase()}</Tag>
      ),
    },
    {
      title: "Data Sources",
      dataIndex: "data_source_count",
      key: "data_source_count",
      render: (count) => (
        <Space>
          <CloudUploadOutlined />
          <Text>{count || 0}</Text>
        </Space>
      ),
    },
    {
      title: "Template",
      dataIndex: "template",
      key: "template",
      render: (template) =>
        template ? (
          <Space>
            <FileTextOutlined />
            <Text>{template.name}</Text>
          </Space>
        ) : (
          <Text type="secondary">No template</Text>
        ),
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (isActive) => (
        <Tag color={isActive ? "green" : "orange"}>
          {isActive ? "Active" : "Inactive"}
        </Tag>
      ),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (date) => new Date(date).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      width: 100,
      render: (_, record) => (
        <Popconfirm
          title="Delete Project"
          description="Are you sure you want to delete this project?"
          onConfirm={(e) => {
            e.stopPropagation();
            handleDeleteProject(record.id);
          }}
          onCancel={(e) => e.stopPropagation()}
          okText="Delete"
          cancelText="Cancel"
          okButtonProps={{ danger: true }}
        >
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={(e) => e.stopPropagation()}
          />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="lookup-project-list">
      <div className="lookup-header">
        <div>
          <Title level={3}>Look-Up Projects</Title>
          <Text type="secondary">
            Manage your static data enrichment projects
          </Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateModalOpen(true)}
        >
          Create Project
        </Button>
      </div>

      <Card>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Search
            placeholder="Search projects..."
            prefix={<SearchOutlined />}
            allowClear
            enterButton
            size="large"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ maxWidth: 400 }}
          />

          <Table
            columns={columns}
            dataSource={filteredProjects}
            loading={loading}
            rowKey="id"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `Total ${total} projects`,
            }}
          />
        </Space>
      </Card>

      <CreateProjectModal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onCreate={handleCreateProject}
      />
    </div>
  );
}
