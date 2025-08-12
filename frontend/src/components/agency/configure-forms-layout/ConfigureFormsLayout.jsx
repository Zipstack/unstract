import PropTypes from "prop-types";

import { SettingsForm } from "../settings-form/SettingsForm";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

import "./ConfigureFormsLayout.css";

function ConfigureFormsLayout({
  specConfig,
  formDataConfig,
  setFormDataConfig,
  isSpecConfigLoading,
}) {
  // First check: Still loading
  if (isSpecConfigLoading) {
    return (
      <div className="config-content-area">
        <SpinnerLoader text="Loading configuration..." />
      </div>
    );
  }

  // Second check: Loaded but empty/failed
  if (!specConfig || Object.keys(specConfig || {})?.length === 0) {
    return (
      <div className="config-content-area">
        <EmptyState text="Failed to load the configuration form" />
      </div>
    );
  }

  return (
    <div className="config-content-area">
      <SettingsForm
        spec={specConfig}
        formData={formDataConfig}
        setFormData={setFormDataConfig}
        isLoading={isSpecConfigLoading}
      />
    </div>
  );
}

ConfigureFormsLayout.propTypes = {
  specConfig: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
  isSpecConfigLoading: PropTypes.bool.isRequired,
};

export { ConfigureFormsLayout };
