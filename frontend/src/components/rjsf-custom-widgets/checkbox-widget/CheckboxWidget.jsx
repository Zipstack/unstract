import { Checkbox, Space, Typography } from "antd";
import PropTypes from "prop-types";
import "./CheckboxWidget.css";
import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown";
const CheckboxWidget = ({ id, value, onChange, label, schema }) => {
  const description = schema?.description || "";
  const handleCheckboxChange = (event) => {
    onChange(event.target.checked);
  };

  return (
    <Space direction="vertical" className="checkbox-widget-main">
      <Checkbox id={id} checked={value} onChange={handleCheckboxChange}>
        <Typography>{label}</Typography>
      </Checkbox>
      {description?.length > 0 && (
        <CustomMarkdown
          text={description}
          isSecondary={true}
          styleClassName="rjsf-helper-font"
        />
      )}
    </Space>
  );
};

CheckboxWidget.propTypes = {
  id: PropTypes.string.isRequired,
  value: PropTypes.bool,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
};

export { CheckboxWidget };
