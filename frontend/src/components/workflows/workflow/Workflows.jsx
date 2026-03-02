import { PlusOutlined, UserOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import isEmpty from "lodash/isEmpty";
import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useCoOwnerManagement } from "../../../hooks/useCoOwnerManagement.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import {
  useInitialFetchCount,
  usePromptStudioModal,
} from "../../../hooks/usePromptStudioFetchCount";
import { useAlertStore } from "../../../store/alert-store";
import { usePromptStudioStore } from "../../../store/prompt-studio-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { usePromptStudioService } from "../../api/prompt-studio-service";
import { PromptStudioModal } from "../../common/PromptStudioModal";
import { ViewTools } from "../../custom-tools/view-tools/ViewTools.jsx";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar.jsx";
import { CoOwnerManagement } from "../../widgets/co-owner-management/CoOwnerManagement.jsx";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { LazyLoader } from "../../widgets/lazy-loader/LazyLoader.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { workflowService } from "./workflow-service";
import "./Workflows.css";

const PROJECT_FILTER_OPTIONS = [
  { label: "My Workflows", value: "mine" },
  { label: "Organization Workflows", value: "all" },
];

const { Title, Text } = Typography;

function Workflows() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectApiService = workflowService();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();

  const initialFetchComplete = useInitialFetchCount(
    fetchCount,
    getPromptStudioCount,
  );

  const [projectList, setProjectList] = useState();
  const [editingProject, setEditProject] = useState();
  const [loading, setLoading] = useState(false);
  const [openModal, toggleModal] = useState(true);
  const projectListRef = useRef();
  const filterViewRef = useRef(PROJECT_FILTER_OPTIONS[0].value);
  const [backendErrors, setBackendErrors] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState();
  const [sharePermissionEdit, setSharePermissionEdit] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const { setAlertDetails } = useAlertStore();
  const {
    coOwnerOpen,
    setCoOwnerOpen,
    coOwnerData,
    coOwnerLoading,
    coOwnerAllUsers,
    coOwnerResourceId,
    handleCoOwner: handleCoOwnerAction,
    onAddCoOwner,
    onRemoveCoOwner,
  } = useCoOwnerManagement({
    service: projectApiService,
    setAlertDetails,
    onListRefresh: () => getProjectList(),
  });
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
      item.workflow_name.toLowerCase().includes(searchText.toLowerCase()),
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
        setAlertDetails({
          type: "success",
          content: "Workflow updated successfully",
        });
        getProjectList();
      })
      .catch((err) => {
        setAlertDetails(
          handleException(
            err,
            `Unable to update workflow ${editingProject.id}`,
          ),
        );
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

  const checkWorkflowUsage = async (id) => {
    const res = await projectApiService.canUpdate(id);
    const data = res?.data || {};
    return {
      canUpdate: data.can_update || false,
      pipelines: data.pipelines || [],
      apiNames: data.api_names || [],
      pipelineCount: data.pipeline_count || 0,
      apiCount: data.api_count || 0,
    };
  };

  const getUsageMessage = (workflowName, usage) => {
    const { pipelines, apiNames, pipelineCount, apiCount } = usage;
    const totalCount = pipelineCount + apiCount;
    if (totalCount === 0) {
      return `Cannot delete \`${workflowName}\` as it is currently in use.`;
    }

    const displayLimit = 3;
    const lines = [];

    if (apiNames.length > 0) {
      const shown = apiNames.slice(0, displayLimit);
      shown.forEach((name) => {
        lines.push(`- \`${name}\` (API Deployment)`);
      });
      if (apiCount > shown.length) {
        lines.push(
          `- ...and ${apiCount - shown.length} more API deployment(s)`,
        );
      }
    }

    if (pipelines.length > 0) {
      const shown = pipelines.slice(0, displayLimit);
      shown.forEach((p) => {
        const name = p.pipeline_name;
        const type = p.pipeline_type;
        lines.push(`- \`${name}\` (${type} Pipeline)`);
      });
      const remaining = pipelineCount - shown.length;
      if (remaining > 0) {
        lines.push(`- ...and ${remaining} more pipeline(s)`);
      }
    }

    const details = lines.join("\n");
    return `Cannot delete \`${workflowName}\` as it is used in:\n${details}`;
  };

  const deleteProject = async (_evt, project) => {
    try {
      const usage = await checkWorkflowUsage(project.id);
      if (usage.canUpdate) {
        projectApiService
          .deleteProject(project.id)
          .then(() => {
            getProjectList();
            setAlertDetails({
              type: "success",
              content: "Workflow deleted successfully",
            });
          })
          .catch((err) => {
            setAlertDetails(
              handleException(err, `Unable to delete workflow ${project.id}`),
            );
          });
      } else {
        setAlertDetails({
          type: "error",
          content: getUsageMessage(project.workflow_name, usage),
        });
      }
    } catch (err) {
      setAlertDetails(
        handleException(err, `Unable to delete workflow ${project.id}`),
      );
    }
  };

  function closeNewProject() {
    setEditProject();
  }

  const handleShare = async (event, workflow, isEdit) => {
    event.stopPropagation();
    setSelectedWorkflow(workflow);
    setSharePermissionEdit(isEdit);
    setShareLoading(true);

    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        projectApiService.getAllUsers(),
        projectApiService.getSharedUsers(workflow.id),
      ]);

      const userList =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      // Pass the complete user list - SharePermission component will handle filtering
      setAllUsers(userList);
      setSelectedWorkflow(sharedUsersResponse.data);
      setShareOpen(true);
    } catch (err) {
      setAlertDetails(
        handleException(err, `Unable to fetch sharing information`),
      );
    } finally {
      setShareLoading(false);
    }
  };

  const onShare = async (selectedUsers, workflow, shareWithEveryone) => {
    setShareLoading(true);
    try {
      await projectApiService.updateSharing(
        workflow.id,
        selectedUsers,
        shareWithEveryone,
      );
      setShareOpen(false);
      setAlertDetails({
        type: "success",
        content: "Workflow sharing updated successfully",
      });
      getProjectList(); // Refresh the list
    } catch (error) {
      setAlertDetails(
        handleException(error, "Unable to update workflow sharing"),
      );
    } finally {
      setShareLoading(false);
    }
  };

  const handleCoOwner = (event, workflow) => {
    event.stopPropagation();
    handleCoOwnerAction(workflow.id);
  };

  const handleNewWorkflowBtnClick = () => {
    showNewProject();
    toggleModal(true);

    try {
      setPostHogCustomEvent("intent_new_wf_project", {
        info: "Clicked on '+ New Workflow' button",
      });
    } catch (_err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const CustomButtons = () => {
    return (
      <CustomButton
        type="primary"
        icon={<PlusOutlined />}
        onClick={handleNewWorkflowBtnClick}
      >
        New Workflow
      </CustomButton>
    );
  };

  // Using the custom hook to manage modal state
  const { showModal, handleModalClose } = usePromptStudioModal(
    initialFetchComplete,
    isLoading,
    count,
  );

  return (
    <>
      {showModal && (
        <PromptStudioModal onClose={handleModalClose} showModal={showModal} />
      )}
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
              handleShare={handleShare}
              handleCoOwner={handleCoOwner}
              titleProp="workflow_name"
              descriptionProp="description"
              idProp="id"
              type="Workflow"
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
              backendErrors={backendErrors}
              setBackendErrors={setBackendErrors}
            />
          )}
          {shareOpen && selectedWorkflow && (
            <LazyLoader
              component={() =>
                import("../../widgets/share-permission/SharePermission.jsx")
              }
              componentName={"SharePermission"}
              open={shareOpen}
              setOpen={setShareOpen}
              sharedItem={selectedWorkflow}
              permissionEdit={sharePermissionEdit}
              loading={shareLoading}
              allUsers={allUsers}
              onApply={onShare}
              isSharableToOrg={true}
            />
          )}
          {coOwnerOpen && (
            <CoOwnerManagement
              open={coOwnerOpen}
              setOpen={setCoOwnerOpen}
              resourceId={coOwnerResourceId}
              resourceType="Workflow"
              allUsers={coOwnerAllUsers}
              coOwners={coOwnerData.coOwners}
              createdBy={coOwnerData.createdBy}
              loading={coOwnerLoading}
              onAddCoOwner={onAddCoOwner}
              onRemoveCoOwner={onRemoveCoOwner}
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
