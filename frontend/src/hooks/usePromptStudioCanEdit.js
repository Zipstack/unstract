import { canEditResource } from "../helpers/resourceAccess";
import { useCustomToolStore } from "../store/custom-tool-store";
import { useSessionStore } from "../store/session-store";

/**
 * Whether the current user may change the Prompt Studio project being viewed.
 *
 * Pairs with the existing `isPublicSource` flag rather than replacing it:
 * that one means "opened through a public read-only link" and also selects
 * API paths, while this one means "shared with me, so read only".
 */
function usePromptStudioCanEdit() {
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  return canEditResource(details, sessionDetails);
}

export { usePromptStudioCanEdit };
