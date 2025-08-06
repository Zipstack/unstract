import PropTypes from "prop-types";

import { SettingsForm } from "../settings-form/SettingsForm";
import { EmptyState } from "../../widgets/empty-state/EmptyState";

import "./ConfigureFormsLayout.css";

function ConfigureFormsLayout({
  handleUpdate,
  specConfig,
  formDataConfig,
  setFormDataConfig,
  isSpecConfigLoading,
}) {
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
        handleUpdate={handleUpdate}
        spec={specConfig}
        formData={formDataConfig}
        setFormData={setFormDataConfig}
        isLoading={isSpecConfigLoading}
      />
    </div>
  );
}

ConfigureFormsLayout.propTypes = {
  handleUpdate: PropTypes.func.isRequired,
  specConfig: PropTypes.object,
  formDataConfig: PropTypes.object,
  setFormDataConfig: PropTypes.func.isRequired,
  isSpecConfigLoading: PropTypes.bool.isRequired,
};

export { ConfigureFormsLayout };
