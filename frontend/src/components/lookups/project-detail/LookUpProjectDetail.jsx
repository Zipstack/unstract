import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Tabs, Typography, Button, Spin } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";

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

export function LookUpProjectDetail() {
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("reference");

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
    {
      key: "debug",
      label: "Debug",
      children: <DebugTab project={project} />,
    },
  ];

  return (
    <div className="lookup-project-detail">
      <div className="project-header">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate("../")}
          className="project-back-btn"
        />
        <Title level={4} className="project-name">
          {project.name}
        </Title>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </div>
  );
}
