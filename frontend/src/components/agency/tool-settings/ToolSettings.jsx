import PropTypes from "prop-types";
import { createRef, useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { RjsfFormLayout } from "../../../layouts/rjsf-form-layout/RjsfFormLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
import { useWorkflowStore } from "../../../store/workflow-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import "./ToolSettings.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";

function ToolSettings({ spec, isSpecLoading }) {
  const formRef = createRef(null);
  const [formData, setFormData] = useState({});
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const { toolSettings } = useToolSettingsStore();
  const { updateMetadata, getMetadata, isLoading } = useWorkflowStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    // Set existing metadata
    const toolInstanceId = toolSettings?.id;
    const metadata = getMetadata(toolInstanceId);
    setFormData(metadata);
  }, [toolSettings, spec]);

  const isFormValid = () => {
    if (formRef) {
      formRef?.current?.validateFields((errors, values) => {
        if (errors) {
          return false;
        }
      });
    }
    return true;
  };

  const validateAndSubmit = (updatedFormData) => {
    if (!isFormValid()) {
      return;
    }
    handleSubmit(updatedFormData);
  };

  const handleSubmit = (updatedFormData) => {
    setFormData(updatedFormData);
    const metadata = { ...updatedFormData };

    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_instance/${toolSettings?.id}/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: { metadata },
    };
    axiosPrivate(requestOptions)
      .then(() => {
        updateMetadata(toolSettings?.id, formData);
        setAlertDetails({
          type: "success",
          content: "Updated tool settings.",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  return (
    <div className="tool-settings-layout">
      <RjsfFormLayout
        schema={spec}
        formData={formData}
        setFormData={setFormData}
        isLoading={isSpecLoading}
        validateAndSubmit={validateAndSubmit}
        formRef={formRef}
        isStateUpdateRequired={true}
      >
        <div className="display-flex-right tool-settings-submit-btn">
          <CustomButton
            type="primary"
            block
            htmlType="submit"
            disabled={isLoading}
          >
            Save
          </CustomButton>
        </div>
      </RjsfFormLayout>
    </div>
  );
}

ToolSettings.propTypes = {
  spec: PropTypes.object,
  isSpecLoading: PropTypes.bool,
};

export { ToolSettings };
