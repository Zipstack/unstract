import {
  AppstoreOutlined,
  BarsOutlined,
  ClearOutlined,
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  MoreOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Card,
  Dropdown,
  Input,
  List,
  Popconfirm,
  Segmented,
  Typography,
} from "antd";
import debounce from "lodash/debounce";
import isEmpty from "lodash/isEmpty";
import PropTypes from "prop-types";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { handleException } from "../../../helpers/GetStaticData.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { LazyLoader } from "../../widgets/lazy-loader/LazyLoader.jsx";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./Workflows.css";
import { workflowService } from "./workflow-service";

const PROJECT_FILTER_OPTIONS = [
  { label: "My Workflows", value: "mine" },
  { label: "Organization Workflows", value: "all" },
];
const PROJECT_VIEW_OPTIONS = [
  {
    value: "grid",
    icon: <AppstoreOutlined />,
  },
  {
    value: "list",
    icon: <BarsOutlined />,
  },
];

const { Title, Text, Paragraph } = Typography;
const { Search } = Input;
const { Item } = List;

function Workflows() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectApiService = workflowService();

  const [projectList, setProjectList] = useState();
  const [viewType, setViewType] = useState(PROJECT_VIEW_OPTIONS[0].value);
  const [editingProject, setEditProject] = useState();
  const [loading, setLoading] = useState(false);
  const [openModal, toggleModal] = useState(true);
  const projectListRef = useRef();
  const filterViewRef = useRef(PROJECT_FILTER_OPTIONS[0].value);

  const { setAlertDetails } = useAlertStore();
  const sessionDetails = useSessionStore((state) => state?.sessionDetails);
  const { updateWorkflow } = useWorkflowStore();
  const orgName = sessionDetails?.orgName;

  useEffect(() => {
    if (location.pathname === `/${orgName}/workflows`) {
      getProjectList();
    }
  }, [location.pathname]);

  function getProjectList() {
    projectApiService
      .getProjectList(filterViewRef.current === PROJECT_FILTER_OPTIONS[0].value)
      .then((res) => {
        projectListRef.current = res.data;
        setProjectList(res.data);
      })
      .catch(() => {
        console.error("Unable to get project list");
      });
  }

  const onSearchDebounce = useCallback(
    debounce((value) => {
      onSearch(value);
    }, 600),
    []
  );

  function onSearch(searchText) {
    if (!searchText.trim()) {
      setProjectList(projectListRef.current);
      return;
    }
    const filteredList = projectListRef.current.filter((item) =>
      item.workflow_name.toLowerCase().includes(searchText.toLowerCase())
    );
    setProjectList(filteredList);
  }

  function applyFilter(value) {
    filterViewRef.current = value;
    projectListRef.current = "";
    setProjectList("");
    getProjectList();
  }

  function editProject(name, description) {
    setLoading(true);
    projectApiService
      .editProject(name, description, editingProject?.id)
      .then((res) => {
        closeNewProject();
        if (editingProject?.name) {
          getProjectList();
        } else {
          openProject(res.data);
        }
        getProjectList();
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }

  function changeView(value) {
    setViewType(value);
  }

  function openProject(project) {
    updateWorkflow({ projectName: project?.workflow_name });
    navigate(`/${orgName}/workflows/${project.id}`);
  }

  function showNewProject() {
    setEditProject({ name: "", description: "" });
  }

  function updateProject(evt, project) {
    toggleModal(true);
    evt.domEvent.stopPropagation();
    setEditProject({
      name: project.workflow_name,
      description: project.description || "",
      id: project.id,
    });
  }

  function clearCache(evt, project) {
    evt.domEvent.stopPropagation();
    projectApiService
      .clearCache(project.id)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Cache cleared successfully",
        });
      })
      .catch(() => {
        setAlertDetails({
          type: "error",
          content: "Unable to clear cache",
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }

  function clearFileMarkers(evt, project) {
    evt.domEvent.stopPropagation();
    projectApiService
      .clearFileMarkers(project.id)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "File markers cleared successfully",
        });
      })
      .catch(() => {
        setAlertDetails({
          type: "error",
          content: "Unable to clear file markers",
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }

  const canDeleteProject = async (id) => {
    let status = false;
    await projectApiService.canUpdate(id).then((res) => {
      status = res?.data?.can_update || false;
    });
    return status;
  };

  const deleteProject = async (evt, project) => {
    evt.stopPropagation();
    const canDelete = await canDeleteProject(project.id);
    if (canDelete) {
      projectApiService
        .deleteProject(project.id)
        .then(() => {
          getProjectList();
          setAlertDetails({
            type: "success",
            content: "Workflow deleted successfully",
          });
        })
        .catch(() => {
          setAlertDetails({
            type: "error",
            content: `Unable to delete workflow ${project.id}`,
          });
        });
    } else {
      setAlertDetails({
        type: "error",
        content:
          "Cannot delete this Workflow, since it is used in one or many of the API/ETL/Task pipelines",
      });
    }
  };

  function closeNewProject() {
    setEditProject();
  }

  return (
    <div className="workflows-pg-layout">
      <div className="workflows-pg-body">
        <div className="header">
          <Segmented options={PROJECT_FILTER_OPTIONS} onChange={applyFilter} />
          <div className="headerPart">
            <Segmented
              options={PROJECT_VIEW_OPTIONS}
              value={viewType}
              onChange={changeView}
            />
            <Search
              disabled={isEmpty(projectListRef?.current)}
              placeholder="Search by name"
              onChange={(e) => onSearchDebounce(e.target.value)}
              allowClear
            />
            <CustomButton
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                showNewProject();
                toggleModal(true);
              }}
            >
              New Workflow
            </CustomButton>
          </div>
        </div>
        <div className="list-of-workflows-body">
          {!projectListRef.current && <SpinnerLoader />}
          {projectListRef.current && isEmpty(projectListRef?.current) && (
            <EmptyState
              text="No Workflow available"
              btnText="New Workflow"
              handleClick={() => {
                showNewProject();
                toggleModal(true);
              }}
            />
          )}
          {isEmpty(projectList) && !isEmpty(projectListRef?.current) && (
            <div className="center">
              <Title level={5}>No results found for this search</Title>
            </div>
          )}
        </div>
        {!isEmpty(projectList) &&
          viewType === PROJECT_VIEW_OPTIONS[0].value && (
            <div className="cardsListWrapper">
              <div className="cardsList">
                {projectList?.map((project) => {
                  return (
                    <Card
                      key={project.id}
                      style={{ width: "100%" }}
                      size="small"
                      type="inner"
                      hoverable
                      extra={
                        <Dropdown
                          menu={{
                            items: [
                              {
                                label: "Edit",
                                key: "edit",
                                icon: <EditOutlined />,
                                onClick: (evt) => updateProject(evt, project),
                              },
                              {
                                label: "Clear Cache",
                                key: "clear_cache",
                                icon: <ClearOutlined />,
                                onClick: (evt) => clearCache(evt, project),
                              },
                              {
                                label: "Clear File Markers",
                                key: "clear_file_markers",
                                icon: <HistoryOutlined />,
                                onClick: (evt) =>
                                  clearFileMarkers(evt, project),
                              },
                              {
                                label: (
                                  <Popconfirm
                                    title="Delete the project"
                                    description="Are you sure to delete this project?"
                                    okText="Yes"
                                    cancelText="No"
                                    icon={
                                      <QuestionCircleOutlined
                                        style={{
                                          color: "#dc4446",
                                        }}
                                      />
                                    }
                                    onConfirm={(evt) => {
                                      deleteProject(evt, project);
                                    }}
                                  >
                                    <Text type="danger">
                                      <DeleteOutlined
                                        style={{
                                          color: "#dc4446",
                                          marginInlineEnd: "8px",
                                        }}
                                      />
                                      Delete
                                    </Text>
                                  </Popconfirm>
                                ),
                                key: "delete",
                                onClick: (evt) =>
                                  evt.domEvent.stopPropagation(),
                              },
                            ],
                          }}
                          trigger={["click"]}
                          placement="bottomRight"
                          onClick={(evt) => evt.stopPropagation()}
                        >
                          <MoreOutlined />
                        </Dropdown>
                      }
                      title={project.workflow_name}
                      onClick={() => openProject(project)}
                    >
                      <div className="cardContent">
                        <Paragraph
                          type="secondary"
                          ellipsis={{
                            rows: project.owner ? 3 : 4,
                            tooltip: project.description,
                          }}
                        >
                          {project.description || "No description provided"}
                        </Paragraph>
                        <User name={project.owner} />
                      </div>
                    </Card>
                  );
                })}
              </div>
            </div>
          )}
        {!isEmpty(projectList) &&
          viewType === PROJECT_VIEW_OPTIONS[1].value && (
            <List
              size="large"
              dataSource={projectList}
              style={{ marginInline: "4px" }}
              className="listWrapper"
              renderItem={(project) => {
                return (
                  <Item
                    key={project.id}
                    className="cur-pointer"
                    onClick={() => openProject(project)}
                    extra={
                      <Dropdown
                        menu={{
                          items: [
                            {
                              label: "Edit",
                              key: "edit",
                              icon: <EditOutlined />,
                              onClick: (evt) => updateProject(evt, project),
                            },
                            {
                              label: (
                                <Popconfirm
                                  title="Delete the project"
                                  description="Are you sure to delete this project?"
                                  okText="Yes"
                                  cancelText="No"
                                  icon={
                                    <QuestionCircleOutlined
                                      style={{
                                        color: "dc4446",
                                      }}
                                    />
                                  }
                                  onConfirm={(evt) => {
                                    deleteProject(evt, project);
                                  }}
                                >
                                  <Text type="danger">
                                    <DeleteOutlined
                                      style={{
                                        color: "#dc4446",
                                        marginInlineEnd: "8px",
                                      }}
                                    />
                                    Delete
                                  </Text>
                                </Popconfirm>
                              ),
                              key: "delete",
                              onClick: (evt) => evt.domEvent.stopPropagation(),
                            },
                          ],
                        }}
                        trigger={["click"]}
                        placement="bottomRight"
                      >
                        <MoreOutlined />
                      </Dropdown>
                    }
                  >
                    <SpaceWrapper
                      className="listItem"
                      onClick={() => openProject(project)}
                    >
                      <Text strong ellipsis>
                        {project.workflow_name}
                      </Text>
                      <Text type="secondary" ellipsis>
                        {project.description || "No description provided"}
                      </Text>
                      <User name={project.owner} />
                    </SpaceWrapper>
                  </Item>
                );
              }}
            />
          )}
        {editingProject && (
          <LazyLoader
            component={() => import("../new-workflow/NewWorkflow.jsx")}
            componentName={"NewWorkflow"}
            name={editingProject.name}
            description={editingProject.description}
            onDone={editProject}
            onClose={closeNewProject}
            loading={loading}
            toggleModal={toggleModal}
            openModal={openModal}
          />
        )}
      </div>
    </div>
  );
}

function User({ name }) {
  return name ? (
    <div className="sessionDetails">
      <UserOutlined />
      <Text italic ellipsis>
        {name}
      </Text>
    </div>
  ) : null;
}

User.propTypes = {
  name: PropTypes.string,
};

export { Workflows };
