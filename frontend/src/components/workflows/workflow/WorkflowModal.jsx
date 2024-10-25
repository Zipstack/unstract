import PropTypes from "prop-types";
import { useState } from "react";
import { LazyLoader } from "../../widgets/lazy-loader/LazyLoader.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { useWorkflowStore } from "../../../store/workflow-store";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../../../store/session-store";

function WorkflowModal({
  open,
  setOpen,
  editItem,
  isEdit,
  handleAddItem,
  loading,
  backendErrors,
}) {
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const [localBackendErrors, setLocalBackendErrors] = useState(backendErrors);
  const navigate = useNavigate();
  const { updateWorkflow } = useWorkflowStore();
  const sessionDetails = useSessionStore((state) => state?.sessionDetails);
  const orgName = sessionDetails?.orgName ?? "";

  const handleOnDone = (name, description) => {
    handleAddItem({ name, description }, isEdit, editItem?.id)
      .then((project) => {
        if (!isEdit) {
          updateWorkflow({ projectName: project?.workflow_name ?? "" });
          navigate(`/${orgName}/workflows/${project?.id ?? ""}`);
        }
        setAlertDetails({
          type: "success",
          content: "Workflow updated successfully",
        });
        setOpen(false);
      })
      .catch((err) => {
        handleException(err, "", setLocalBackendErrors);
      });
  };

  const handleOnClose = () => {
    setOpen(false);
  };

  return (
    <LazyLoader
      component={() => import("../new-workflow/NewWorkflow.jsx")}
      componentName="NewWorkflow"
      name={editItem?.workflow_name ?? ""}
      description={editItem?.description ?? ""}
      onDone={handleOnDone}
      onClose={handleOnClose}
      loading={loading}
      openModal={open}
      backendErrors={localBackendErrors}
      setBackendErrors={setLocalBackendErrors}
    />
  );
}

WorkflowModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editItem: PropTypes.shape({
    id: PropTypes.number,
    workflow_name: PropTypes.string,
    description: PropTypes.string,
  }),
  isEdit: PropTypes.bool.isRequired,
  handleAddItem: PropTypes.func.isRequired,
  loading: PropTypes.bool.isRequired,
  backendErrors: PropTypes.any,
  setBackendErrors: PropTypes.func.isRequired,
};

export default WorkflowModal;
