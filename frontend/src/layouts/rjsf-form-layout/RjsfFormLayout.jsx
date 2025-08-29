import { useCallback, useMemo } from "react";
import Form from "@rjsf/antd";
import validator from "@rjsf/validator-ajv8";
import PropTypes from "prop-types";
import { Alert, Space } from "antd";

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
import CustomMarkdown from "../../components/helpers/custom-markdown/CustomMarkdown.jsx";
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

  const transformErrors = useCallback(
    (errors) => {
      return errors.map((error) => {
        const { name, params, property } = error;

        // Try to resolve nested schema/title from property path like ".a.b[0].c"
        const path = (property || "").replace(/^\./, "");
        const getFieldSchema = (root, pathStr) => {
          if (!root || !pathStr) return undefined;
          const tokens = pathStr
            .replace(/\[(\d+)\]/g, ".$1")
            .split(".")
            .filter(Boolean);
          let cur = root;
          for (const tok of tokens) {
            if (cur?.type === "array" && cur?.items) {
              cur = cur.items;
            }
            if (cur?.properties && cur.properties[tok]) {
              cur = cur.properties[tok];
            }
          }
          return cur;
        };
        const schemaProps = schema?.properties ?? {};
        const fieldSchema = getFieldSchema(schema, path);
        const fieldName = path;
        const fieldTitle = fieldSchema?.title || fieldName || "This field";

        // Special handling for "required", since Ajv attaches it at parent level
        if (name === "required") {
          const missingField = params?.missingProperty;
          const missingSchema = schemaProps[missingField];
          const missingTitle =
            missingSchema?.title || missingField || "This field";

          return {
            ...error,
            message: `'${missingTitle}' is required`,
          };
        }

        switch (name) {
          // Numeric validations
          case "minimum":
            return {
              ...error,
              message: `'${fieldTitle}' must be at least ${params?.limit}`,
            };

          case "maximum":
            return {
              ...error,
              message: `'${fieldTitle}' must not exceed ${params?.limit}`,
            };

          case "exclusiveMinimum":
            return {
              ...error,
              message: `'${fieldTitle}' must be greater than ${params?.limit}`,
            };

          case "exclusiveMaximum":
            return {
              ...error,
              message: `'${fieldTitle}' must be less than ${params?.limit}`,
            };

          case "multipleOf":
            return {
              ...error,
              message: `'${fieldTitle}' must be a multiple of ${params?.multipleOf}`,
            };

          // String validations
          case "minLength":
            return {
              ...error,
              message: `'${fieldTitle}' must be at least ${params?.limit} characters`,
            };

          case "maxLength":
            return {
              ...error,
              message: `'${fieldTitle}' must not exceed ${params?.limit} characters`,
            };

          case "pattern":
            return {
              ...error,
              message: `'${fieldTitle}' must match the required format`,
            };

          // Array validations
          case "minItems":
            return {
              ...error,
              message: `'${fieldTitle}' must have at least ${params?.limit} items`,
            };

          case "maxItems":
            return {
              ...error,
              message: `'${fieldTitle}' must not exceed ${params?.limit} items`,
            };

          case "uniqueItems":
            return {
              ...error,
              message: `'${fieldTitle}' must contain only unique items`,
            };

          // Object validations
          case "minProperties":
            return {
              ...error,
              message: `'${fieldTitle}' must have at least ${params?.limit} properties`,
            };

          case "maxProperties":
            return {
              ...error,
              message: `'${fieldTitle}' must not exceed ${params?.limit} properties`,
            };

          // Other validations
          case "enum": {
            let enumMessage = `'${fieldTitle}' must be one of the allowed values`;
            if (fieldSchema?.enumNames && fieldSchema.enumNames.length > 0) {
              const options = fieldSchema.enumNames;
              const maxShow = 4; // Maximum options to show before truncating

              if (options.length <= maxShow) {
                // Show all options if list is small
                enumMessage = `'${fieldTitle}' must be one of: ${options.join(
                  ", "
                )}`;
              } else {
                // Truncate long lists with "and X others" suffix
                const firstFew = options.slice(0, maxShow).join(", ");
                const remaining = options.length - maxShow;
                enumMessage = `'${fieldTitle}' must be one of: ${firstFew} (and ${remaining} ${
                  remaining === 1 ? "other" : "others"
                })`;
              }
            }

            return {
              ...error,
              message: enumMessage,
            };
          }

          case "const":
            return {
              ...error,
              message: `'${fieldTitle}' must be exactly ${params?.allowedValue}`,
            };

          case "type":
            return {
              ...error,
              message: `'${fieldTitle}' must be of type ${params?.type}`,
            };

          case "format":
            return {
              ...error,
              message: `'${fieldTitle}' must be a valid ${params?.format}`,
            };

          case "additionalProperties":
            return {
              ...error,
              message: `'${fieldTitle}' has an unsupported property '${params?.additionalProperty}'`,
            };

          case "dependentRequired":
            return {
              ...error,
              message: `'${fieldTitle}' requires '${params?.missingProperty}'`,
            };

          default:
            // fallback: try to use Ajv stack if meaningful
            if (error.stack?.trim()) {
              return { ...error, message: error.stack };
            }
            return { ...error, message: `'${fieldTitle}': ${error.message}` };
        }
      });
    },
    [schema]
  );

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
            ref={formRef}
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
            templates={{
              FieldTemplate: CustomFieldTemplate,
            }}
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
