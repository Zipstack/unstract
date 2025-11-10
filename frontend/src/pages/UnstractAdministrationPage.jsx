let UnstractAdministration;

try {
  UnstractAdministration =
    require("../plugins/subscription-admin/components/UnstractAdministration.jsx").UnstractAdministration;
} catch (err) { // NOSONAR - Plugin loading pattern: Cloud-only feature gracefully handled
  // Cloud-only feature, not available in OSS
}

function UnstractAdministrationPage() {
  if (!UnstractAdministration) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <h2>Administration Panel</h2>
        <p>This feature is only available in Unstract Cloud.</p>
      </div>
    );
  }
  return <UnstractAdministration />;
}

export { UnstractAdministrationPage };
