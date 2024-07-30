import { useEffect, useState, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import PropTypes from "prop-types";
import { Button, Space, Typography } from "antd";
import { ArrowLeftOutlined, QuestionCircleOutlined } from "@ant-design/icons";

import "./MenuLayout.css";
import { useSessionStore } from "../../store/session-store";
import { useWorkflowStore } from "../../store/workflow-store";

function MenuLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const currentMenu = useRef();
  const [activeTab, setActiveTab] = useState("");
  const { sessionDetails } = useSessionStore();
  const { projectName } = useWorkflowStore();

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

  return (
    <div className="flex-dir-col overflow-hidden">
      <div className="appHeader">
        <div className="project_detail">
          <Button
            size="small"
            type="text"
            onClick={() => navigate(`/${sessionDetails.orgName}/workflows`)}
          >
            <ArrowLeftOutlined />
          </Button>
          <Typography className="proj_name">
            {projectName || "Name of the project"}
          </Typography>
        </div>
        <div>
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
        </div>
      </div>
      <div className="appBody overflow-hidden">
        <div className="appBody2">{children}</div>
      </div>
    </div>
  );
}

MenuLayout.propTypes = {
  children: PropTypes.oneOfType([PropTypes.node, PropTypes.element]),
};

export { MenuLayout };
