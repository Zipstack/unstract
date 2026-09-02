import { canEditResource } from "../helpers/resourceAccess";
import { useSessionStore } from "../store/session-store";
import { useWorkflowStore } from "../store/workflow-store";

/**
 * Whether the current user may change the workflow being viewed.
 *
 * Thin wrapper over `canEditResource` for the workflow builder, which reads
 * its resource from the workflow store rather than a list row.
 */
function useWorkflowCanEdit() {
  const { details } = useWorkflowStore();
  const { sessionDetails } = useSessionStore();
  return canEditResource(details, sessionDetails);
}

export { useWorkflowCanEdit };
