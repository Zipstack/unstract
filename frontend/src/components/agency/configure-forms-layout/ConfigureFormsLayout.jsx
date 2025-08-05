import PropTypes from "prop-types";

import { SettingsForm } from "../settings-form/SettingsForm";
import { EmptyState } from "../../widgets/empty-state/EmptyState";

function ConfigureFormsLayout({
  handleUpdate,
  specConfig,
  formDataConfig,
  setFormDataConfig,
  isSpecConfigLoading,
}) {
  if (!specConfig || Object.keys(specConfig || {})?.length === 0) {
    return <EmptyState text="Failed to load the configuration form" />;
  }

  return (
    <SettingsForm
      handleUpdate={handleUpdate}
      spec={specConfig}
      formData={formDataConfig}
      setFormData={setFormDataConfig}
      isLoading={isSpecConfigLoading}
    />
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
