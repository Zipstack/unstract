import { BranchesOutlined } from "@ant-design/icons";
import { Divider, Image, Layout, Space, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";
import "./SideNavBar.css";
const { Sider } = Layout;

import Workflows from "../../../assets/Workflows.svg";
import apiDeploy from "../../../assets/api-deployments.svg";
import CustomTools from "../../../assets/custom-tools-icon.svg";
import EmbeddingIcon from "../../../assets/embedding.svg";
import etl from "../../../assets/etl.svg";
import LlmIcon from "../../../assets/llm.svg";
import PlatformSettingsIcon from "../../../assets/platform-settings.svg";
import task from "../../../assets/task.svg";
import VectorDbIcon from "../../../assets/vector-db.svg";
import TextExtractorIcon from "../../../assets/text-extractor.svg";
import { useSessionStore } from "../../../store/session-store";

let getMenuItem;
try {
  getMenuItem = require("../../../plugins/app-deployments/app-deployment-components/helpers/getMenuItem");
} catch (err) {
  // Plugin unavailable.
}

const SideNavBar = ({ collapsed }) => {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, flags } = sessionDetails;

  const data = [
    {
      id: 1,
      mainTitle: "MANAGE",
      subMenu: [
        {
          id: 1.1,
          title: "API Deployments",
          description: "Unstructured to structured APIs",
          image: apiDeploy,
          path: `/${orgName}/api`,
          active: window.location.pathname.startsWith(`/${orgName}/api`),
        },
        {
          id: 1.3,
          title: "ETL Pipelines",
          description: "Unstructured to structured data pipelines",
          image: etl,
          path: `/${orgName}/etl`,
          active: window.location.pathname.startsWith(`/${orgName}/etl`),
        },
        {
          id: 1.4,
          title: "Task Pipelines",
          description: "Ad-hoc unstructured data task pipelines",
          image: task,
          path: `/${orgName}/task`,
          active: window.location.pathname.startsWith(`/${orgName}/task`),
        },
      ],
    },
    {
      id: 2,
      mainTitle: "BUILD",
      subMenu: [
        {
          id: 2.1,
          title: "Workflows",
          description: "Build no-code data workflows for unstructured data",
          icon: BranchesOutlined,
          image: Workflows,
          path: `/${orgName}/workflows`,
          active: window.location.pathname.startsWith(`/${orgName}/workflows`),
        },
        {
          id: 2.2,
          title: "Prompt Studio",
          description: "Create structured data from unstructured documents",
          image: CustomTools,
          path: `/${orgName}/tools`,
          active: window.location.pathname.startsWith(`/${orgName}/tools`),
        },
      ],
    },
    {
      id: 3,
      mainTitle: "SETTINGS",
      subMenu: [
        {
          id: 3.1,
          title: "LLMs",
          description: "Setup platform wide access to Large Language Models",
          icon: BranchesOutlined,
          image: LlmIcon,
          path: `/${orgName}/settings/llms`,
          active: window.location.pathname.startsWith(
            `/${orgName}/settings/llms`
          ),
        },
        {
          id: 3.2,
          title: "Vector DBs",
          description: "Setup platform wide access to Vector DBs",
          image: VectorDbIcon,
          path: `/${orgName}/settings/vectorDbs`,
          active: window.location.pathname.startsWith(
            `/${orgName}/settings/vectorDbs`
          ),
        },
        {
          id: 3.3,
          title: "Embedding",
          description: "Setup platform wide access to Embedding models",
          image: EmbeddingIcon,
          path: `/${orgName}/settings/embedding`,
          active: window.location.pathname.startsWith(
            `/${orgName}/settings/embedding`
          ),
        },
        {
          id: 3.4,
          title: "Text Extractor",
          description: "Setup platform wide access to Text extractor services",
          image: TextExtractorIcon,
          path: `/${orgName}/settings/textExtractor`,
          active: window.location.pathname.startsWith(
            `/${orgName}/settings/textExtractor`
          ),
        },
        {
          id: 3.5,
          title: "Platform",
          description: "Settings for the platform",
          image: PlatformSettingsIcon,
          path: `/${orgName}/settings`,
          active:
            window.location.pathname === `/${orgName}/settings` ||
            window.location.pathname === `/${orgName}/settings/platform` ||
            window.location.pathname === `/${orgName}/settings/triad` ||
            window.location.pathname === `/${orgName}/users`,
        },
      ],
    },
  ];

  if (getMenuItem && flags.app_deployment) {
    data[0].subMenu.splice(1, 0, getMenuItem.default(orgName));
  }

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={collapsed}
      className="side-bar"
      width={240}
      collapsedWidth={65}
    >
      <div className="main-slider">
        <div className="slider-wrap">
          {data?.map((item, index) => {
            return (
              <div key={item?.id}>
                {!collapsed && (
                  <Typography className="sidebar-main-heading">
                    {item.mainTitle}
                  </Typography>
                )}
                <Space direction="vertical" className="menu-item-body">
                  {item.subMenu.map((el) => {
                    return (
                      <Tooltip key={el.id} title={collapsed ? el.title : ""}>
                        <Space
                          className={`space-styles ${
                            el.active ? "space-styles-active" : ""
                          } ${el.disable ? "space-styles-disable" : ""}`}
                          onClick={() => {
                            !el.disable && navigate(el.path);
                          }}
                        >
                          <Image
                            src={el.image}
                            alt="side_icon"
                            className="menu-item-icon"
                            preview={false}
                          />
                          {!collapsed && (
                            <div>
                              <Typography className="sidebar-item-text fs-14">
                                {el.title}
                              </Typography>
                              <Typography className="sidebar-item-text fs-11">
                                {el.description}
                              </Typography>
                            </div>
                          )}
                        </Space>
                      </Tooltip>
                    );
                  })}
                </Space>
                {index < data.length - 1 && (
                  <Divider className="sidebar-divider" />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Sider>
  );
};

SideNavBar.propTypes = {
  collapsed: PropTypes.bool.isRequired,
};

export default SideNavBar;
