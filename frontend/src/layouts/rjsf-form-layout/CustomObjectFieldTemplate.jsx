import { Row, Col } from "antd";
import PropTypes from "prop-types";
import "./CustomFieldTemplate.css";

const CustomObjectFieldTemplate = (props) => {
  const { properties, title, description, formData } = props;

  // Create a map of properties by name for easy lookup
  const propertyMap = {};
  properties.forEach((prop) => {
    propertyMap[prop.name] = prop;
  });

  // Define field order for file connector forms (this template is only used for forms with file expiry fields)
  const fieldOrder = [
    "folders",
    "processSubDirectories",
    "fileExtensions",
    "maxFiles",
    "fileReprocessingHandling",
    // Conditional fields at bottom:
    "reprocessInterval",
    "intervalUnit",
  ];

  // Auto-detect if we have file expiry fields that should be rendered side-by-side
  const hasFileExpiryFields =
    propertyMap["reprocessInterval"] && propertyMap["intervalUnit"];

  // Filter fields based on conditions
  const shouldShowConditionalFields =
    formData?.fileReprocessingHandling === "reprocess_after_interval";

  return (
    <div>
      {title && <h3>{title}</h3>}
      {description && <p>{description}</p>}

      {fieldOrder.map((fieldName) => {
        const property = propertyMap[fieldName];
        if (!property) return null;

        // Skip conditional fields when they shouldn't be shown
        if (
          (fieldName === "reprocessInterval" || fieldName === "intervalUnit") &&
          !shouldShowConditionalFields
        ) {
          return null;
        }

        // Handle file expiry fields side-by-side layout
        if (
          hasFileExpiryFields &&
          (fieldName === "reprocessInterval" || fieldName === "intervalUnit")
        ) {
          // Render both fields together when we hit reprocessInterval
          if (
            fieldName === "reprocessInterval" &&
            shouldShowConditionalFields
          ) {
            const intervalProperty = propertyMap["reprocessInterval"];
            const unitProperty = propertyMap["intervalUnit"];

            if (intervalProperty && unitProperty) {
              return (
                <Row
                  key="conditional-fields"
                  gutter={[4, 2]}
                  className="compact-expiry-fields"
                >
                  <Col span={12}>{intervalProperty.content}</Col>
                  <Col span={12}>{unitProperty.content}</Col>
                </Row>
              );
            }
          }
          // Skip intervalUnit as it's already rendered with reprocessInterval
          if (fieldName === "intervalUnit") {
            return null;
          }
        }

        // Default rendering for regular fields
        return (
          <div key={fieldName} className="property-wrapper">
            {property.content}
          </div>
        );
      })}
    </div>
  );
};

CustomObjectFieldTemplate.propTypes = {
  properties: PropTypes.array.isRequired,
  uiSchema: PropTypes.object,
  title: PropTypes.string,
  description: PropTypes.string,
  formData: PropTypes.object,
};

export { CustomObjectFieldTemplate };
