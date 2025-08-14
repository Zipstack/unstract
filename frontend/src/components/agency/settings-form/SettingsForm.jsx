import PropTypes from "prop-types";

import { RjsfFormLayout } from "../../../layouts/rjsf-form-layout/RjsfFormLayout";

function SettingsForm({ spec, formData, setFormData, isLoading }) {
  return (
    <RjsfFormLayout
      schema={spec}
      formData={formData}
      setFormData={setFormData}
      isLoading={isLoading}
      isStateUpdateRequired={true}
    />
  );
}

SettingsForm.propTypes = {
  spec: PropTypes.object,
  formData: PropTypes.object,
  setFormData: PropTypes.func.isRequired,
  isLoading: PropTypes.bool.isRequired,
};

export { SettingsForm };
