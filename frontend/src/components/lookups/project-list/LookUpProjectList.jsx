import { Button, Input, Tag, Typography, Popconfirm } from "antd";
import {
  PlusOutlined,
  SearchOutlined,
  DeleteOutlined,
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CalendarOutlined,
  DatabaseOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { CreateProjectModal } from "../create-project-modal/CreateProjectModal";
import "./LookUpProjectList.css";

const { Title, Text } = Typography;

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

  return (
    <div className="lookup-project-list">
      <div className="lookup-header">
        <div className="lookup-header-left">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(-1)}
            className="lookup-back-btn"
          />
          <Title level={4} className="lookup-title">
            Look-Up Projects
          </Title>
        </div>
        <div className="lookup-header-right">
          <Input
            placeholder="Search any project"
            prefix={<SearchOutlined />}
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="lookup-search-input"
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            Create Project
          </Button>
        </div>
      </div>

      <div className="lookup-cards-container">
        {loading ? (
          <div className="lookup-loading">Loading...</div>
        ) : filteredProjects.length === 0 ? (
          <div className="lookup-empty">
            <Text type="secondary">
              {searchText
                ? "No projects match your search"
                : "No projects yet. Create one to get started."}
            </Text>
          </div>
        ) : (
          filteredProjects.map((project) => (
            <div key={project.id} className="lookup-project-card">
              <div className="lookup-card-header">
                <Button
                  type="link"
                  className="lookup-card-title"
                  onClick={() => navigate(project.id)}
                >
                  {project.name}
                </Button>
                <Popconfirm
                  title="Delete Project"
                  description="Are you sure you want to delete this project?"
                  onConfirm={() => handleDeleteProject(project.id)}
                  okText="Delete"
                  cancelText="Cancel"
                  okButtonProps={{ danger: true }}
                >
                  <Button
                    type="text"
                    icon={<DeleteOutlined />}
                    className="lookup-card-delete"
                  />
                </Popconfirm>
              </div>

              <div className="lookup-card-body">
                <div className="lookup-card-row">
                  <Text className="lookup-card-label">DATA SOURCES</Text>
                  <div className="lookup-card-value">
                    <DatabaseOutlined className="lookup-card-icon" />
                    <Text>{project.data_source_count || 0}</Text>
                  </div>
                </div>

                <div className="lookup-card-row">
                  <Text className="lookup-card-label">TEMPLATE</Text>
                  <div className="lookup-card-value">
                    <FileTextOutlined className="lookup-card-icon" />
                    <Text>{project.template?.name || "No template"}</Text>
                  </div>
                </div>

                <div className="lookup-card-row">
                  <Text className="lookup-card-label">STATUS</Text>
                  <div className="lookup-card-value">
                    <CheckCircleOutlined
                      className="lookup-card-icon"
                      style={{
                        color: project.is_active ? "#52c41a" : "#faad14",
                      }}
                    />
                    <Tag
                      color={project.is_active ? "green" : "orange"}
                      className="lookup-status-tag"
                    >
                      {project.is_active ? "Active" : "Inactive"}
                    </Tag>
                  </div>
                </div>

                <div className="lookup-card-row">
                  <Text className="lookup-card-label">CREATED</Text>
                  <div className="lookup-card-value">
                    <CalendarOutlined className="lookup-card-icon" />
                    <Text>
                      {new Date(project.created_at).toLocaleDateString()}
                    </Text>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <CreateProjectModal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onCreate={handleCreateProject}
      />
    </div>
  );
}
