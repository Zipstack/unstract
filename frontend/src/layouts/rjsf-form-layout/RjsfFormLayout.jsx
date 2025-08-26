import Form from "@rjsf/antd";
import validator from "@rjsf/validator-ajv8";
import { Alert, Space } from "antd";
import PropTypes from "prop-types";
import { useCallback, useMemo } from "react";

import CustomMarkdown from "../../components/helpers/custom-markdown/CustomMarkdown.jsx";
import { AltDateTimeWidget } from "../../components/rjsf-custom-widgets/alt-date-time-widget/AltDateTimeWidget.jsx";
import { AltDateWidget } from "../../components/rjsf-custom-widgets/alt-date-widget/AltDateWidget.jsx";
import { ArrayField } from "../../components/rjsf-custom-widgets/array-field/ArrayField.jsx";
import { CheckboxWidget } from "../../components/rjsf-custom-widgets/checkbox-widget/CheckboxWidget.jsx";
import { CheckboxesWidget } from "../../components/rjsf-custom-widgets/checkboxes-widget/CheckboxesWidget.jsx";
import { ColorWidget } from "../../components/rjsf-custom-widgets/color-widget/ColorWidget.jsx";
import { DateTimeWidget } from "../../components/rjsf-custom-widgets/date-time-widget/DateTimeWidget.jsx";
import { DateWidget } from "../../components/rjsf-custom-widgets/date-widget/DateWidget.jsx";
import { EmailWidget } from "../../components/rjsf-custom-widgets/email-widget/EmailWidget.jsx";
import { FileWidget } from "../../components/rjsf-custom-widgets/file-widget/FileWidget.jsx";
import { HiddenWidget } from "../../components/rjsf-custom-widgets/hidden-widget/HiddenWidget.jsx";
import { PasswordWidget } from "../../components/rjsf-custom-widgets/password-widget/PasswordWidget.jsx";
import { SelectWidget } from "../../components/rjsf-custom-widgets/select-widget/SelectWidget.jsx";
import { TextWidget } from "../../components/rjsf-custom-widgets/text-widget/TextWidget.jsx";
import { TimeWidget } from "../../components/rjsf-custom-widgets/time-widget/TimeWidget.jsx";
import { UpDownWidget } from "../../components/rjsf-custom-widgets/up-down-widget/UpDownWidget.jsx";
import { URLWidget } from "../../components/rjsf-custom-widgets/url-widget/URLWidget.jsx";
import { SpinnerLoader } from "../../components/widgets/spinner-loader/SpinnerLoader.jsx";
import { CustomFieldTemplate } from "./CustomFieldTemplate.jsx";
import { CustomObjectFieldTemplate } from "./CustomObjectFieldTemplate.jsx";
import "./RjsfFormLayout.css";

function RjsfFormLayout({
  children,
  schema,
  formData,
  setFormData,
  isLoading,
  formRef,
  validateAndSubmit,
  isStateUpdateRequired,
}) {
  const formSchema = useMemo(() => {
    if (!schema) return {};
    const rest = { ...schema };
    delete rest.title;
    delete rest.description;
    return rest;
  }, [schema]);

  const description = useMemo(() => schema?.description || "", [schema]);

  const widgets = useMemo(
    () => ({
      AltDateTimeWidget,
      AltDateWidget,
      CheckboxWidget,
      CheckboxesWidget,
      ColorWidget,
      DateTimeWidget,
      DateWidget,
      EmailWidget,
      FileWidget,
      HiddenWidget,
      PasswordWidget,
      SelectWidget,
      TextWidget,
      TimeWidget,
      UpDownWidget,
      URLWidget,
    }),
    []
  );

  const fields = useMemo(
    () => ({
      ArrayField,
    }),
    []
  );

  const uiSchema = useMemo(
    () => ({
      "ui:classNames": "my-rjsf-form",
    }),
    [formData]
  );

  const removeBlankDefault = useCallback((schema) => {
    if (schema?.properties && schema?.required) {
      const properties = schema.properties;
      schema.required.forEach((key) => {
        if (
          properties[key] &&
          (properties[key].default === null || properties[key].default === "")
        ) {
          delete properties[key].default;
        }
      });
    }
    return schema;
  }, []);

  const transformErrors = useCallback((errors) => {
    return errors.map((error) => {
      if (error.name === "required") {
        return {
          ...error,
          message: "This field is mandatory. Please provide a value.",
        };
      }
      return error;
    });
  }, []);

  const handleChange = useCallback(
    (event) => {
      if (!isStateUpdateRequired) {
        return;
      }
      const data = event.formData;
      setFormData(data);
    },
    [isStateUpdateRequired, setFormData]
  );

  // Apply CustomObjectFieldTemplate for file connector forms (those with fileReprocessingHandling)
  const templates = useMemo(() => {
    const isFileConnectorForm =
      !!formSchema?.properties?.fileReprocessingHandling;

    return isFileConnectorForm
      ? {
          FieldTemplate: CustomFieldTemplate,
          ObjectFieldTemplate: CustomObjectFieldTemplate,
        }
      : {
          FieldTemplate: CustomFieldTemplate,
          // No ObjectFieldTemplate - use RJSF default for tool settings etc.
        };
  }, [formSchema]);

  return (
    <>
      {isLoading ? (
        <SpinnerLoader />
      ) : (
        <Space direction="vertical" className="width-100">
          {description && (
            <Alert
              message={<CustomMarkdown text={description} />}
              type="info"
            />
          )}
          <Form
            form={formRef}
            schema={removeBlankDefault(formSchema)}
            uiSchema={uiSchema}
            validator={validator}
            widgets={widgets}
            fields={fields}
            formData={formData}
            transformErrors={transformErrors}
            onError={() => {}}
            onSubmit={(e) => validateAndSubmit?.(e.formData)}
            showErrorList={false}
            onChange={handleChange}
            templates={templates}
          >
            {children || <></>}
          </Form>
        </Space>
      )}
    </>
  );
}

RjsfFormLayout.propTypes = {
  children: PropTypes.oneOfType([PropTypes.node, PropTypes.element]),
  schema: PropTypes.object.isRequired,
  formData: PropTypes.object,
  setFormData: PropTypes.func,
  isLoading: PropTypes.bool.isRequired,
  validateAndSubmit: PropTypes.func,
  formRef: PropTypes.object,
  isStateUpdateRequired: PropTypes.bool,
};

export { RjsfFormLayout };
