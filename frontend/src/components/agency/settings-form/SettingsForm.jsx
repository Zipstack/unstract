import PropTypes from "prop-types";
import { RjsfFormLayout } from "../../../layouts/rjsf-form-layout/RjsfFormLayout";
import { CustomButton } from "../../widgets/custom-button/CustomButton";

function SettingsForm({
  spec,
  formData,
  setFormData,
  isLoading,
  handleUpdate,
}) {
  const handleSave = () => {
    handleUpdate({ configuration: formData }, true);
  };

  return (
    <RjsfFormLayout
      schema={spec}
      formData={formData}
      setFormData={setFormData}
      isLoading={isLoading}
      validateAndSubmit={handleSave}
      isStateUpdateRequired={true}
    >
      <div className="display-flex-right tool-settings-submit-btn">
        <CustomButton type="primary" htmlType="submit">
          Save
        </CustomButton>
      </div>
    </RjsfFormLayout>
  );
}

SettingsForm.propTypes = {
  spec: PropTypes.object,
  formData: PropTypes.object,
  setFormData: PropTypes.func.isRequired,
  isLoading: PropTypes.bool.isRequired,
  handleUpdate: PropTypes.func.isRequired,
};

export { SettingsForm };
