import { useState, useEffect } from "react";
import { Row, Col, Card, Statistic, Button } from "antd";
import {
  ProjectOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

import { useMockApi } from "../hooks/useMockApi";

const Dashboard = () => {
  const [stats, setStats] = useState({
    total_projects: 0,
    total_documents: 0,
    completed_extractions: 0,
    pending_extractions: 0,
  });
  const { getProjects } = useMockApi();
  const navigate = useNavigate();

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const projects = await getProjects();
      // TODO: Replace with actual stats API
      setStats({
        total_projects: projects.length,
        total_documents: 42,
        completed_extractions: 35,
        pending_extractions: 7,
      });
    } catch (error) {
      console.error("Failed to fetch stats:", error);
    }
  };

  return (
    <div style={{ padding: "24px" }}>
      <h1 style={{ marginBottom: "24px" }}>Dashboard</h1>

      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Projects"
              value={stats.total_projects}
              prefix={<ProjectOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Documents"
              value={stats.total_documents}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Completed Extractions"
              value={stats.completed_extractions}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Pending Extractions"
              value={stats.pending_extractions}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: "#faad14" }}
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginTop: "24px" }}>
        <h3>Quick Actions</h3>
        <Button type="primary" onClick={() => navigate("/projects")}>
          View All Projects
        </Button>
      </Card>
    </div>
  );
};

export default Dashboard;
