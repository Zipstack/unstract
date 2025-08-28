import PropTypes from "prop-types";
import { createRef, useEffect, useState } from "react";
import { Empty, Typography } from "antd";

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

  // Transform adapter names to IDs for validation compatibility
  const transformAdapterNamesToIds = (metadata, schema) => {
    if (!metadata || !schema?.properties) {
      return metadata || {};
    }

    const transformedMetadata = { ...metadata };

    // Find all fields that have enum and enumNames (these are adapter fields)
    Object.keys(schema.properties).forEach((fieldName) => {
      const fieldSchema = schema.properties[fieldName];
      if (
        fieldSchema?.enum &&
        fieldSchema?.enumNames &&
        transformedMetadata[fieldName]
      ) {
        const currentValue = transformedMetadata[fieldName];

        // Find the index of the current name in enumNames
        const nameIndex = fieldSchema.enumNames.indexOf(currentValue);
        if (nameIndex !== -1 && fieldSchema.enum[nameIndex]) {
          // Replace name with corresponding ID from enum array
          transformedMetadata[fieldName] = fieldSchema.enum[nameIndex];
        } else {
          // Handle case where adapter name is not found (possibly deleted/renamed)
          console.warn(
            `[ToolSettings] WARNING - Adapter '${currentValue}' for field '${fieldName}' not found in available options:`,
            fieldSchema.enumNames
          );
          // Keep the original value, backend will handle the validation error
        }
      }
    });

    return transformedMetadata;
  };

  useEffect(() => {
    // Set existing metadata
    const toolInstanceId = toolSettings?.id;
    const metadata = getMetadata(toolInstanceId);
    const transformedMetadata = transformAdapterNamesToIds(metadata, spec);
    setFormData(transformedMetadata);
  }, [toolSettings, spec]);

  const isObjectEmpty = (obj) => {
    return obj && Object.keys(obj).length === 0;
  };

  const validateAndSubmit = (updatedFormData) => {
    if (formRef && !formRef.current?.validateForm()) {
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

  // Show empty state for Prompt Studio tools that don't have configurable settings
  if (
    !isSpecLoading &&
    (isObjectEmpty(spec) || isObjectEmpty(spec?.properties))
  ) {
    return (
      <div className="tool-settings-layout">
        <Empty
          description={
            <div style={{ textAlign: "center" }}>
              <Typography.Text type="secondary">
                This Prompt Studio tool doesn&apos;t have configurable settings.
              </Typography.Text>
              <br />
              <Typography.Text type="secondary" style={{ fontSize: "12px" }}>
                Tool configuration is managed within the Prompt Studio
                interface.
              </Typography.Text>
            </div>
          }
        />
      </div>
    );
  }

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
