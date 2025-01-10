import { Select } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

import "./ArrayField.css";

const ArrayField = (props) => {
  const { schema, formData, onChange, required, readonly } = props;
  const [dropdownList, setDropdownList] = useState([]);
  const [options, setOptions] = useState([]);

  useEffect(() => {
    if (Array.isArray(schema?.items?.enum)) {
      setDropdownList(schema?.items?.enum);
    }
  }, []);

  useEffect(() => {
    if (dropdownList?.length > 0) {
      const opts = dropdownList.map((item) => {
        return { value: item, label: item };
      });
      setOptions(opts);
    }
  }, [dropdownList]);

  const handleChange = (values) => {
    if (!values?.length) {
      onChange([]);
      return;
    }

    const latestValue = values[values?.length - 1];
    if (dropdownList?.length && !dropdownList.includes(latestValue)) {
      return;
    }

    onChange(values);
  };

  return (
    <RjsfWidgetLayout
      label={schema?.title}
      description={schema?.description}
      required={required}
    >
      <Select
        mode="tags"
        allowClear
        className="array-field-select"
        placeholder="Please select"
        value={formData}
        onChange={handleChange}
        options={options}
        disabled={readonly}
      />
    </RjsfWidgetLayout>
  );
};

ArrayField.propTypes = {
  items: PropTypes.object,
  schema: PropTypes.object.isRequired,
  formData: PropTypes.array,
  onChange: PropTypes.func.isRequired,
  required: PropTypes.bool,
  readonly: PropTypes.bool.isRequired,
};

export { ArrayField };
