import { useSessionStore } from "../store/session-store";

// Builds `/api/v1/unstract/<orgId>/<path>` for the signed-in org. `orgId` is
// read at call time, so call this inside the request, not at module scope.
const orgApi = (path = "") => {
  const { orgId } = useSessionStore.getState().sessionDetails ?? {};
  return `/api/v1/unstract/${orgId}/${path.replace(/^\/+/, "")}`;
};

export { orgApi };
