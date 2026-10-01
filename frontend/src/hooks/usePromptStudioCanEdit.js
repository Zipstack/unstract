import { canEditResource } from "../helpers/resourceAccess";
import { useCustomToolStore } from "../store/custom-tool-store";
import { useSessionStore } from "../store/session-store";

/**
 * Whether the current user owns the Prompt Studio project being viewed.
 *
 * Gates the owner-only controls, which for Prompt Studio is the project name:
 * prompts and settings stay editable for everyone it is shared with.
 *
 * Pairs with the existing `isPublicSource` flag rather than replacing it:
 * that one means "opened through a public read-only link" and also selects
 * API paths.
 */
function usePromptStudioCanEdit() {
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  return canEditResource(details, sessionDetails);
}

export { usePromptStudioCanEdit };
