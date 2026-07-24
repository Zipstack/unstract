import { PlusOutlined, UserOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useCoOwnerManagement } from "../../../hooks/useCoOwnerManagement.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import {
  applyPagedResponse,
  buildPagedParams,
  usePaginatedList,
} from "../../../hooks/usePaginatedList";
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
import { groupsService } from "../../groups/groups-service.js";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar.jsx";
import { CoOwnerModal } from "../../widgets/co-owner-management/CoOwnerModal.jsx";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import { EmptyState } from "../../widgets/empty-state/EmptyState.jsx";
import { LazyLoader } from "../../widgets/lazy-loader/LazyLoader.jsx";
import { ResourceTable } from "../../widgets/resource-table/ResourceTable.jsx";
import { SharePermission } from "../../widgets/share-permission/SharePermission.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { workflowService } from "./workflow-service";
import "./Workflows.css";

const { Text } = Typography;

const DEFAULT_PAGE_SIZE = 10;

function Workflows() {
  const navigate = useNavigate();
  const location = useLocation();
  const projectApiService = workflowService();
  const groupsApi = groupsService();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { count, isLoading, fetchCount } = usePromptStudioStore();
  const { getPromptStudioCount } = usePromptStudioService();

  const initialFetchComplete = useInitialFetchCount(
    fetchCount,
    getPromptStudioCount,
  );

  const [projectList, setProjectList] = useState();
  // Fetch failure (vs. genuinely empty) — drives a retryable error state.
  const [loadError, setLoadError] = useState(false);
  const [editingProject, setEditProject] = useState();
  const [loading, setLoading] = useState(false);
  // Modal-local save spinner — kept off the shared list-loading so an edit can't
  // race the post-edit refetch for the list's loading state.
  const [editLoading, setEditLoading] = useState(false);
  const [openModal, toggleModal] = useState(true);
  // Monotonic request token so a stale response can't overwrite a newer one.
  const seqRef = useRef(0);
  const [backendErrors, setBackendErrors] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState();
  const [sharePermissionEdit, setSharePermissionEdit] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [allGroups, setAllGroups] = useState([]);

  const { setAlertDetails } = useAlertStore();

  const {
    pagination,
    setPagination,
    searchTerm,
    sort,
    fetchRef,
    requestList,
    syncRequested,
    handlePaginationChange,
    handleSearch,
    handleSortChange,
    handleListRefresh,
  } = usePaginatedList({ defaultPageSize: DEFAULT_PAGE_SIZE });
  const coOwner = useCoOwnerManagement({
    service: projectApiService,
    setAlertDetails,
    onListRefresh: handleListRefresh,
  });
  const sessionDetails = useSessionStore((state) => state?.sessionDetails);
  const { updateWorkflow } = useWorkflowStore();
  const orgName = sessionDetails?.orgName;

  useEffect(() => {
    if (location.pathname === `/${orgName}/workflows`) {
      getProjectList();
    }
  }, [location.pathname]);

  const getProjectList = (
    page = 1,
    pageSize = DEFAULT_PAGE_SIZE,
    search = "",
    sortBy = "",
    order = "asc",
  ) => {
    const params = buildPagedParams({ page, pageSize, search, sortBy, order });
    const seq = ++seqRef.current;
    setLoadError(false);
    setLoading(true);
    return projectApiService
      .getProjectList(params)
      .then((res) =>
        applyPagedResponse({
          data: res?.data,
          page,
          pageSize,
          seq,
          latestSeqRef: seqRef,
          setList: setProjectList,
          setPagination,
          refetchPrevPage: () =>
            requestList(page - 1, pageSize, search, sortBy, order),
        }),
      )
      .catch(() => {
        // A newer request superseded this one — don't surface its error.
        if (seq !== seqRef.current) {
          return;
        }
        console.error("Unable to get project list");
        // Surface a retryable error instead of a misleading empty state.
        setLoadError(true);
        // Failed request — realign requestedRef with the still-shown view.
        syncRequested();
      })
      .finally(() => {
        // Only the newest request owns the shared loading state.
        if (seq === seqRef.current) {
          setLoading(false);
        }
      });
  };
  fetchRef.current = getProjectList;

  function editProject(name, description) {
    // Drive the modal-local editLoading, not the shared list-loading: on success
    // the edit path's handleListRefresh owns the list spinner (new path navigates
    // away), so editProject can't clear a pending refetch's loading.
    setEditLoading(true);
    projectApiService
      .editProject(name, description, editingProject?.id)
      .then((res) => {
        closeNewProject();
        if (editingProject?.name) {
          handleListRefresh();
        } else {
          openProject(res.data);
        }
        setAlertDetails({
          type: "success",
          content: "Workflow updated successfully",
        });
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
        setEditLoading(false);
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
            handleListRefresh();
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
      const [usersResponse, sharedUsersResponse, groupsResponse] =
        await Promise.all([
          projectApiService.getAllUsers(),
          projectApiService.getSharedUsers(workflow.id),
          groupsApi.listGroups(),
        ]);

      const userList =
        usersResponse?.data?.members?.map((member) => ({
          id: member.id,
          email: member.email,
        })) || [];

      // Pass the complete user list - SharePermission component will handle filtering
      setAllUsers(userList);
      setAllGroups(
        Array.isArray(groupsResponse?.data)
          ? groupsResponse.data.map((g) => ({
              id: g.id,
              name: g.name,
            }))
          : [],
      );
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

  const onShare = async (
    selectedUsers,
    workflow,
    shareWithEveryone,
    selectedGroups = [],
  ) => {
    setShareLoading(true);
    try {
      await projectApiService.updateSharing(
        workflow.id,
        selectedUsers,
        shareWithEveryone,
        selectedGroups,
      );
      setAlertDetails({
        type: "success",
        content: "Workflow sharing updated successfully",
      });
      handleListRefresh();
      // Close only on success; keep the modal open on failure so the user
      // can see the rejected entries and retry.
      setShareOpen(false);
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
    coOwner.handleCoOwner(workflow.id);
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

  const newWorkflowButton = (
    <CustomButton
      type="primary"
      icon={<PlusOutlined />}
      onClick={handleNewWorkflowBtnClick}
    >
      New Workflow
    </CustomButton>
  );

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
        title="Workflows"
        enableSearch
        customButtons={newWorkflowButton}
        onSearch={(value) => handleSearch(value)}
      />
      <div className="workflows-pg-layout">
        <div className="workflows-pg-body">
          {projectList === undefined && !loadError && <SpinnerLoader />}
          {projectList === undefined && loadError && (
            <EmptyState
              text="Couldn't load. Please try again."
              btnText="Retry"
              handleClick={handleListRefresh}
            />
          )}
          {projectList?.length === 0 && !searchTerm && (
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
          {projectList?.length === 0 && searchTerm && (
            <EmptyState text="No results found for this search" />
          )}
          {projectList?.length > 0 && (
            <ResourceTable
              dataSource={projectList}
              loading={loading}
              pagination={pagination}
              sort={sort}
              onPaginationChange={handlePaginationChange}
              onSortChange={handleSortChange}
              titleProp="workflow_name"
              descriptionProp="description"
              idProp="id"
              dateProp="created_at"
              ownerEmailProp="created_by_email"
              handleEdit={updateProject}
              handleShare={handleShare}
              handleDelete={deleteProject}
              handleCoOwner={handleCoOwner}
              sessionDetails={sessionDetails}
              showOwner
              isClickable
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
              loading={editLoading}
              toggleModal={toggleModal}
              openModal={openModal}
              backendErrors={backendErrors}
              setBackendErrors={setBackendErrors}
            />
          )}
          {shareOpen && selectedWorkflow && (
            <SharePermission
              open={shareOpen}
              setOpen={setShareOpen}
              adapter={selectedWorkflow}
              permissionEdit={sharePermissionEdit}
              loading={shareLoading}
              allUsers={allUsers}
              allGroups={allGroups}
              onApply={onShare}
              isSharableToOrg={true}
            />
          )}
          {coOwner.coOwnerOpen && (
            <CoOwnerModal coOwner={coOwner} resourceType="Workflow" />
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
