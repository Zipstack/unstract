import { Form, Checkbox } from "antd";
import PropTypes from "prop-types";
import React, { useEffect, useState, useCallback } from "react";

const FilterPromptFields = React.memo(
  ({ isOpen, selectedPrompts, setSelectedPrompts }) => {
    const [localSelectedPrompts, setLocalSelectedPrompts] =
      useState(selectedPrompts);
    const [hasChanges, setHasChanges] = useState(false);
    const [form] = Form.useForm();

    useEffect(() => {
      if (!isOpen && hasChanges) {
        // Update parent state when the Drawer is closed and changes were made
        setSelectedPrompts(localSelectedPrompts);
      }
    }, [isOpen, hasChanges, setSelectedPrompts, localSelectedPrompts]);

    const handleValuesChange = useCallback((_, allValues) => {
      setHasChanges(true);
      setLocalSelectedPrompts(allValues);
    }, []);

    return (
      <Form
        form={form}
        initialValues={localSelectedPrompts}
        onValuesChange={handleValuesChange}
      >
        {Object.keys(localSelectedPrompts).map((key) => (
          <Form.Item key={key} name={key} valuePropName="checked">
            <Checkbox>{key}</Checkbox>
          </Form.Item>
        ))}
      </Form>
    );
  }
);

FilterPromptFields.displayName = "FilterPromptFields";

FilterPromptFields.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  selectedPrompts: PropTypes.object.isRequired,
  setSelectedPrompts: PropTypes.func.isRequired,
};

export { FilterPromptFields };
