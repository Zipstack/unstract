import { QuestionCircleOutlined } from "@ant-design/icons";
import { Checkbox, Space, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import "./CheckboxWidget.css";
const CheckboxWidget = ({ id, value, onChange, label, schema }) => {
  const description = schema?.description || "";
  const handleCheckboxChange = (event) => {
    onChange(event.target.checked);
  };

  return (
    <Space className="checkbox-widget-main">
      <Checkbox id={id} checked={value} onChange={handleCheckboxChange}>
        <Typography>{label}</Typography>
      </Checkbox>
      {description?.length > 0 && (
        <Tooltip title={description}>
          <QuestionCircleOutlined className="checkbox-widget-info-icon" />
        </Tooltip>
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
