// TEST BRANCH ONLY: mounts the v1 preview with the v0 session. Never merged.

import { V1Preview } from "@v1";
import { useSessionStore } from "../store/session-store";

function V1PreviewPage() {
  const { sessionDetails } = useSessionStore();
  const current = sessionDetails?.allOrganization?.find(
    (org) => org.id === sessionDetails?.orgId,
  );
  return (
    <V1Preview
      user={{
        name: sessionDetails?.display_name || sessionDetails?.name || "",
        email: sessionDetails?.email || "",
      }}
      organization={{
        id: sessionDetails?.orgId || "",
        name: sessionDetails?.orgName || "",
        displayName: current?.display_name || sessionDetails?.orgName || "",
      }}
    />
  );
}

export { V1PreviewPage };
