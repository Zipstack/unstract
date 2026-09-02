import { useSessionStore } from "../store/session-store";
import { useWorkflowStore } from "../store/workflow-store";

/**
 * Whether the current user may change the workflow being viewed.
 *
 * Sharing — direct, via group, or org-wide — grants read only. Owners,
 * co-owners and org admins may edit. Mirrors the backend's
 * `is_workflow_mutator`, which is the authority.
 */
function useWorkflowCanEdit() {
  const { details } = useWorkflowStore();
  const { sessionDetails } = useSessionStore();
  return Boolean(details?.is_owner || sessionDetails?.isAdmin);
}

export { useWorkflowCanEdit };
