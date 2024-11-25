import Form from "@rjsf/antd";
import validator from "@rjsf/validator-ajv8";
import PropTypes from "prop-types";

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
import { SelectWidget } from "../../components/rjsf-custom-widgets/select-widget/SelectWidget.jsx";
import { TimeWidget } from "../../components/rjsf-custom-widgets/time-widget/TimeWidget.jsx";
import { URLWidget } from "../../components/rjsf-custom-widgets/url-widget/URLWidget.jsx";
import { SpinnerLoader } from "../../components/widgets/spinner-loader/SpinnerLoader.jsx";
import { TextWidget } from "../../components/rjsf-custom-widgets/text-widget/TextWidget.jsx";
import { PasswordWidget } from "../../components/rjsf-custom-widgets/password-widget/PasswordWidget.jsx";
import { UpDownWidget } from "../../components/rjsf-custom-widgets/up-down-widget/UpDownWidget.jsx";
import { CustomFieldTemplate } from "./CustomFieldTemplate.jsx";
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
  schema.title = "";
  schema.description = "";
  const widgets = {
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
  };

  const fields = {
    ArrayField,
  };

  const uiSchema = {
    "ui:classNames": "my-rjsf-form",
    mark_horizontal_lines: {
      "ui:widget": !formData?.mark_vertical_lines ? "hidden" : undefined,
    },
  };

  const removeBlankDefault = (schema) => {
    /**
     * We are removing the "required fields" default property if the value is null or "".
     * We need this for applying the required field form valiation.
     */
    if (schema?.properties && schema?.required) {
      Object.keys(schema.properties).forEach((key) => {
        if (
          schema.required.includes(key) &&
          (schema.properties[key].default === null ||
            schema.properties[key].default === "")
        ) {
          delete schema.properties[key].default;
        }
      });
    }
    return schema;
  };

  // Change the error message for required fields.
  const transformErrors = (errors) => {
    return errors.map((error) => {
      if (error.name === "required") {
        // Change the error message for the "required" validation
        return {
          ...error,
          message: "This field is mandatory. Please provide a value.",
        };
      }
      return error;
    });
  };

  // If required, the `formData` state can be dynamically updated to store the latest user input as they interact with the form.
  const handleChange = (event) => {
    if (!isStateUpdateRequired) {
      return;
    }
    const data = event.formData;
    setFormData(data);
  };

  return (
    <>
      {isLoading ? (
        <SpinnerLoader />
      ) : (
        <Form
          form={formRef}
          schema={removeBlankDefault(schema)}
          uiSchema={uiSchema}
          validator={validator}
          widgets={widgets}
          fields={fields}
          formData={formData}
          transformErrors={transformErrors}
          onError={() => {}}
          onSubmit={(e) => validateAndSubmit(e.formData)}
          showErrorList={false}
          onChange={handleChange}
          templates={{
            FieldTemplate: CustomFieldTemplate,
          }}
        >
          {children}
        </Form>
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
