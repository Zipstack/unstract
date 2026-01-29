import { useMemo, useState, useEffect, useRef } from "react";
import {
  BranchesOutlined,
  PushpinOutlined,
  PushpinFilled,
} from "@ant-design/icons";
import {
  Divider,
  Image,
  Layout,
  Popover,
  Space,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";

import { useSessionStore } from "../../../store/session-store";
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
import TerminalIcon from "../../../assets/terminal.svg";
import ConnectorsIcon from "../../../assets/connectors.svg";

import "./SideNavBar.css";
import "../../settings/settings/Settings.css";

const { Sider } = Layout;

let getMenuItem;
try {
  getMenuItem = require("../../../plugins/app-deployment/getMenuItem");
} catch (err) {
  // Plugin unavailable.
}

let sideMenu;
try {
  sideMenu = require("../../../plugins/hooks/useSideMenu");
} catch (err) {
  // Plugin unavailable.
}

let unstractSubscriptionPlan;
let unstractSubscriptionPlanStore;
let dashboardSideMenuItem;
let UNSTRACT_SUBSCRIPTION_PLANS;
try {
  unstractSubscriptionPlanStore = require("../../../plugins/store/unstract-subscription-plan-store");
  const unstractSubscriptionConstants = require("../../../plugins/unstract-subscription/helper/constants");
  dashboardSideMenuItem = unstractSubscriptionConstants?.dashboardSideMenuItem;
  UNSTRACT_SUBSCRIPTION_PLANS =
    unstractSubscriptionConstants?.UNSTRACT_SUBSCRIPTION_PLANS;
} catch (err) {
  // Plugin unavailable.
}

let selectedProductStore;
let selectedProduct;
try {
  selectedProductStore = require("../../../plugins/store/select-product-store.js");
} catch {
  // Ignore if hook not available
}

let agenticPromptStudioEnabled = false;
try {
  require("../../../plugins/agentic-prompt-studio");
  agenticPromptStudioEnabled = true;
} catch {
  // Plugin unavailable
}

let manualReviewSettingsEnabled = false;
try {
  require("../../../plugins/manual-review/settings/Settings.jsx");
  manualReviewSettingsEnabled = true;
} catch {
  // Plugin unavailable
}

const getSettingsMenuItems = (orgName) => [
  {
    key: "platform",
    label: "Platform Settings",
    path: `/${orgName}/settings/platform`,
  },
  {
    key: "users",
    label: "User Management",
    path: `/${orgName}/users`,
  },
  {
    key: "triad",
    label: "Default Triad",
    path: `/${orgName}/settings/triad`,
  },
  ...(manualReviewSettingsEnabled
    ? [
        {
          key: "review",
          label: "Human In the Loop Settings",
          path: `/${orgName}/settings/review`,
        },
      ]
    : []),
];

const getActiveSettingsKey = () => {
  const currentPath = globalThis.location.pathname;
  if (currentPath.includes("/settings/platform")) return "platform";
  if (currentPath.includes("/users")) return "users";
  if (currentPath.includes("/settings/triad")) return "triad";
  if (currentPath.includes("/settings/review")) return "review";
  return "platform";
};

const SettingsPopoverContent = ({ orgName, navigate }) => {
  const settingsMenuItems = getSettingsMenuItems(orgName);
  const currentActiveKey = getActiveSettingsKey();

  const handleMenuClick = (path) => {
    navigate(path);
  };

  return (
    <nav className="settings-sidebar-popover">
      {settingsMenuItems.map((menuItem) => (
        <button
          key={menuItem.key}
          type="button"
          className={`settings-menu-item ${
            currentActiveKey === menuItem.key ? "active" : ""
          }`}
          onClick={() => handleMenuClick(menuItem.path)}
        >
          {menuItem.label}
        </button>
      ))}
    </nav>
  );
};

SettingsPopoverContent.propTypes = {
  orgName: PropTypes.string.isRequired,
  navigate: PropTypes.func.isRequired,
};

const SideNavBar = ({ collapsed, setCollapsed }) => {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, flags } = sessionDetails;

  const [isPinned, setIsPinned] = useState(
    JSON.parse(localStorage.getItem("sidebarPinned")) || false
  );
  const collapseTimeoutRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("sidebarPinned", JSON.stringify(isPinned));
  }, [isPinned]);

  const handleMouseEnter = () => {
    if (collapseTimeoutRef.current) {
      clearTimeout(collapseTimeoutRef.current);
    }
    if (!isPinned) {
      setCollapsed(false);
    }
  };

  const handleMouseLeave = () => {
    if (!isPinned) {
      collapseTimeoutRef.current = setTimeout(() => {
        setCollapsed(true);
      }, 300);
    }
  };

  const togglePin = () => {
    const newPinned = !isPinned;
    setIsPinned(newPinned);
    if (newPinned) {
      setCollapsed(false);
    }
  };

  try {
    if (unstractSubscriptionPlanStore?.useUnstractSubscriptionPlanStore) {
      unstractSubscriptionPlan =
        unstractSubscriptionPlanStore?.useUnstractSubscriptionPlanStore(
          (state) => state?.unstractSubscriptionPlan
        );
    }
  } catch (error) {
    // Do nothing
  }

  if (selectedProductStore?.useSelectedProductStore) {
    selectedProduct = selectedProductStore.useSelectedProductStore(
      (state) => state?.selectedProduct
    );
  }

  let menu;
  if (sideMenu) {
    menu = sideMenu.useSideMenu();
  }

  const unstractMenuItems = [
    {
      id: 1,
      mainTitle: "BUILD",
      subMenu: [
        {
          id: 1.1,
          title: "Prompt Studio",
          description: "Create structured data from unstructured documents",
          image: CustomTools,
          path: `/${orgName}/tools`,
          active: globalThis.location.pathname.startsWith(`/${orgName}/tools`),
        },
        {
          id: 1.3,
          title: "Workflows",
          description: "Build no-code data workflows for unstructured data",
          icon: BranchesOutlined,
          image: Workflows,
          path: `/${orgName}/workflows`,
          active: globalThis.location.pathname.startsWith(
            `/${orgName}/workflows`
          ),
        },
      ],
    },
    {
      id: 2,
      mainTitle: "MANAGE",
      subMenu: [
        {
          id: 2.2,
          title: "API Deployments",
          description: "Unstructured to structured APIs",
          image: apiDeploy,
          path: `/${orgName}/api`,
          active: globalThis.location.pathname.startsWith(`/${orgName}/api`),
        },
        {
          id: 2.3,
          title: "ETL Pipelines",
          description: "Unstructured to structured data pipelines",
          image: etl,
          path: `/${orgName}/etl`,
          active: globalThis.location.pathname.startsWith(`/${orgName}/etl`),
        },
        {
          id: 2.4,
          title: "Task Pipelines",
          description: "Ad-hoc unstructured data task pipelines",
          image: task,
          path: `/${orgName}/task`,
          active: globalThis.location.pathname.startsWith(`/${orgName}/task`),
        },
        {
          id: 1.5,
          title: "Logs",
          description: "Records system events for monitoring and debugging",
          image: TerminalIcon,
          path: `/${orgName}/logs`,
          active: globalThis.location.pathname.startsWith(`/${orgName}/logs`),
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
          active: globalThis.location.pathname.startsWith(
            `/${orgName}/settings/llms`
          ),
        },
        {
          id: 3.2,
          title: "Vector DBs",
          description: "Setup platform wide access to Vector DBs",
          image: VectorDbIcon,
          path: `/${orgName}/settings/vectorDbs`,
          active: globalThis.location.pathname.startsWith(
            `/${orgName}/settings/vectorDbs`
          ),
        },
        {
          id: 3.3,
          title: "Embedding",
          description: "Setup platform wide access to Embedding models",
          image: EmbeddingIcon,
          path: `/${orgName}/settings/embedding`,
          active: globalThis.location.pathname.startsWith(
            `/${orgName}/settings/embedding`
          ),
        },
        {
          id: 3.4,
          title: "Text Extractor",
          description: "Setup platform wide access to Text extractor services",
          image: TextExtractorIcon,
          path: `/${orgName}/settings/textExtractor`,
          active: globalThis.location.pathname.startsWith(
            `/${orgName}/settings/textExtractor`
          ),
        },
        {
          id: 3.5,
          title: "Connectors",
          description: "Manage connectors for data sources and destinations",
          image: ConnectorsIcon,
          path: `/${orgName}/settings/connectors`,
          active: globalThis.location.pathname.startsWith(
            `/${orgName}/settings/connectors`
          ),
        },
        {
          id: 3.6,
          title: "Platform",
          description: "Settings for the platform",
          image: PlatformSettingsIcon,
          path: `/${orgName}/settings/platform`,
          active:
            globalThis.location.pathname === `/${orgName}/settings` ||
            globalThis.location.pathname === `/${orgName}/settings/platform` ||
            globalThis.location.pathname === `/${orgName}/settings/triad` ||
            globalThis.location.pathname === `/${orgName}/settings/review` ||
            globalThis.location.pathname === `/${orgName}/users`,
        },
      ],
    },
  ];

  if (dashboardSideMenuItem) {
    unstractMenuItems[1].subMenu.unshift(dashboardSideMenuItem(orgName));
  }

  // If selectedProduct is verticals and menu is null, don't show any sidebar items
  const data =
    selectedProduct === "verticals" && menu === null
      ? []
      : menu || unstractMenuItems;

  if (getMenuItem && flags?.app_deployment) {
    data[1]?.subMenu?.splice(1, 0, getMenuItem.default(orgName));
  }

  // Add Agentic Prompt Studio menu item if plugin is available
  if (agenticPromptStudioEnabled) {
    data[0]?.subMenu?.splice(1, 0, {
      id: 1.2,
      title: "Agentic Prompt Studio",
      description: "Build and manage AI-powered extraction workflows",
      image: CustomTools,
      path: `/${orgName}/agentic-prompt-studio`,
      active: globalThis.location.pathname.startsWith(
        `/${orgName}/agentic-prompt-studio`
      ),
    });
  }

  const shouldDisableAll = useMemo(() => {
    const isUnstract = !(selectedProduct && selectedProduct !== "unstract");
    if (
      !unstractSubscriptionPlan ||
      !UNSTRACT_SUBSCRIPTION_PLANS ||
      !isUnstract
    ) {
      return false;
    }

    return unstractSubscriptionPlan?.remainingDays < 0;
  }, [unstractSubscriptionPlan]);

  data.forEach((mainMenuItem) => {
    mainMenuItem.subMenu.forEach((subMenuItem) => {
      subMenuItem.disable = shouldDisableAll;
    });
  });

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={collapsed}
      className="side-bar"
      width={240}
      collapsedWidth={65}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="sidebar-content-wrapper">
        <div className="main-slider">
          <div className="slider-wrap">
            {data?.map((item, index) => (
              <div key={item?.id}>
                {!collapsed && (
                  <Typography className="sidebar-main-heading">
                    {item.mainTitle}
                  </Typography>
                )}
                <Space direction="vertical" className="menu-item-body">
                  {item.subMenu.map((el) => {
                    // Platform item has a hover menu and click navigates to platform settings
                    if (el.id === 3.6) {
                      const handlePlatformClick = () => {
                        if (!el.disable) {
                          navigate(el.path);
                        }
                      };

                      const platformContent = (
                        <Tooltip title={collapsed ? el.title : ""}>
                          <Space
                            className={`space-styles ${
                              el.active ? "space-styles-active" : ""
                            } ${el.disable ? "space-styles-disable" : ""}`}
                            onClick={handlePlatformClick}
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

                      // Don't show popover when disabled
                      if (el.disable) {
                        return <div key={el.id}>{platformContent}</div>;
                      }

                      return (
                        <Popover
                          key={el.id}
                          content={
                            <SettingsPopoverContent
                              orgName={orgName}
                              navigate={navigate}
                            />
                          }
                          trigger="hover"
                          placement="rightTop"
                          arrow={false}
                          overlayClassName="settings-popover-overlay"
                        >
                          {platformContent}
                        </Popover>
                      );
                    }

                    return (
                      <Tooltip key={el.id} title={collapsed ? el.title : ""}>
                        <Space
                          className={`space-styles ${
                            el.active ? "space-styles-active" : ""
                          } ${el.disable ? "space-styles-disable" : ""}`}
                          onClick={() => {
                            if (!el.disable) {
                              navigate(el.path);
                            }
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
            ))}
          </div>
        </div>
      </div>
      <Tooltip title={isPinned ? "Unpin sidebar" : "Keep expanded"}>
        <div
          className="sidebar-pin-container"
          onClick={togglePin}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              togglePin();
            }
          }}
          role="button"
          tabIndex={0}
        >
          {isPinned ? (
            <PushpinFilled className="sidebar-pin-icon pinned" />
          ) : (
            <PushpinOutlined className="sidebar-pin-icon" />
          )}
        </div>
      </Tooltip>
    </Sider>
  );
};

SideNavBar.propTypes = {
  collapsed: PropTypes.bool.isRequired,
  setCollapsed: PropTypes.func.isRequired,
};

export default SideNavBar;
