import { useEffect, useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";

import { workflowStatus } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { MenuLayout } from "../../../layouts/menu-layout/MenuLayout";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
import { useWorkflowStore } from "../../../store/workflow-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";

function ProjectHelper() {
  const { id } = useParams();
  const { sessionDetails } = useSessionStore();
  const { updateWorkflow, setDefaultWorkflowState } = useWorkflowStore();
  const { cleanUpToolSettings } = useToolSettingsStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const [isWfLoading, setWfLoading] = useState(true);
  const navigate = useNavigate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    return () => {
      cleanUpToolSettings();
      setDefaultWorkflowState();
    };
  }, []);

  useEffect(() => {
    const workflowState = {
      projectId: id,
      isLoading: false,
    };
    updateWorkflow(workflowState);

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${id}/`,
    };
    setWfLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        workflowState["prompt"] = data?.prompt_text;
        workflowState["details"] = data;
        workflowState["status"] = workflowStatus.generated;
        workflowState["isLoading"] = false;
        workflowState["projectName"] = data.workflow_name;
        updateWorkflow(workflowState);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load the workflow"));
        navigate(`/${sessionDetails?.orgName}/workflows`);
      })
      .finally(() => {
        setWfLoading(false);
      });
  }, [id]);

  if (isWfLoading) {
    return <SpinnerLoader />;
  }

  return (
    <MenuLayout>
      <Outlet />
    </MenuLayout>
  );
}

export { ProjectHelper };
