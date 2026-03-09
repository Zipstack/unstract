import "./UnstractAdministrationPage.css";
import { useSessionStore } from "../store/session-store";

let UnstractAdministration;

try {
  const mod = await import(
    "../plugins/subscription-admin/components/UnstractAdministration.jsx"
  );
  UnstractAdministration = mod.UnstractAdministration;
} catch {
  // NOSONAR
  // Cloud-only feature, not available in OSS
}

function UnstractAdministrationPage() {
  const { sessionDetails } = useSessionStore();

  // Wait for session to load before making authorization decisions
  if (!sessionDetails) {
    return null;
  }

  const isStaff = sessionDetails?.isStaff || sessionDetails?.is_staff;
  const orgName = sessionDetails?.orgName;
  const isOpenSource = orgName === "mock_org";

  // Staff permission check - protects route at component level
  if (!isStaff || isOpenSource) {
    return (
      <div className="administration-fallback">
        <h2>Access Denied</h2>
        <p>This feature requires staff permissions.</p>
      </div>
    );
  }

  // Cloud-only feature check
  if (!UnstractAdministration) {
    return (
      <div className="administration-fallback">
        <h2>Administration Panel</h2>
        <p>This feature is only available in Unstract Cloud.</p>
      </div>
    );
  }

  return <UnstractAdministration />;
}

export { UnstractAdministrationPage };
