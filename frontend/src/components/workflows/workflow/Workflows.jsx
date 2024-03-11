import { PlusOutlined, UserOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import isEmpty from "lodash/isEmpty";
import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { handleException } from "../../../helpers/GetStaticData.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { LazyLoader } from "../../widgets/lazy-loader/LazyLoader.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./Workflows.css";
import { workflowService } from "./workflow-service";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar.jsx";
import { ViewTools } from "../../custom-tools/view-tools/ViewTools.jsx";

const PROJECT_FILTER_OPTIONS = [
  { label: "My Workflows", value: "mine" },
  { label: "Organization Workflows", value: "all" },
];

const { Title, Text } = Typography;

function Workflows() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectApiService = workflowService();

  const [projectList, setProjectList] = useState();
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

  function onSearch(searchText, setSearchList) {
    if (!searchText.trim()) {
      setSearchList(projectListRef.current);
      return;
    }
    const filteredList = projectListRef.current.filter((item) =>
      item.workflow_name.toLowerCase().includes(searchText.toLowerCase())
    );
    setSearchList(filteredList);
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

  function openProject(project) {
    updateWorkflow({ projectName: project?.workflow_name });
    navigate(`/${orgName}/workflows/${project.id}`);
  }

  function showNewProject() {
    setEditProject({ name: "", description: "" });
  }

  function updateProject(_event, project) {
    toggleModal(true);
    setEditProject({
      name: project.workflow_name,
      description: project.description || "",
      id: project.id,
    });
  }

  const canDeleteProject = async (id) => {
    let status = false;
    await projectApiService.canUpdate(id).then((res) => {
      status = res?.data?.can_update || false;
    });
    return status;
  };

  const deleteProject = async (_evt, project) => {
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

  const CustomButtons = () => {
    return (
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
    );
  };

  return (
    <>
      <ToolNavBar
        enableSearch
        searchList={projectList}
        setSearchList={setProjectList}
        CustomButtons={CustomButtons}
        segmentFilter={applyFilter}
        segmentOptions={PROJECT_FILTER_OPTIONS}
        onSearch={onSearch}
      />
      <div className="workflows-pg-layout">
        <div className="workflows-pg-body">
          {!projectListRef.current && <SpinnerLoader />}
          {projectListRef.current && isEmpty(projectListRef?.current) && (
            <div className="list-of-workflows-body">
              <EmptyState
                text="No Workflow available"
                btnText="New Workflow"
                handleClick={() => {
                  showNewProject();
                  toggleModal(true);
                }}
              />
            </div>
          )}
          {isEmpty(projectList) && !isEmpty(projectListRef?.current) && (
            <div className="center">
              <Title level={5}>No results found for this search</Title>
            </div>
          )}
          {!isEmpty(projectList) && (
            <ViewTools
              isLoading={loading}
              isEmpty={!projectList?.length}
              listOfTools={projectList}
              setOpenAddTool={toggleModal}
              handleEdit={updateProject}
              handleDelete={deleteProject}
              titleProp="workflow_name"
              descriptionProp="description"
              idProp="id"
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
    </>
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
