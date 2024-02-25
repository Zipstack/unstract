import { UploadOutlined } from "@ant-design/icons";
import { Button, Upload } from "antd";
import PropTypes from "prop-types";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const FileWidget = ({ id, onChange, label, required }) => {
  const handleFileChange = (info) => {
    if (info.file.status === "done") {
      const fileUrl = info.file.response.url; // Assuming the response contains the uploaded file URL
      onChange(fileUrl);
    }
  };

  return (
    <RjsfWidgetLayout label={label} required={required}>
      <Upload id={id} onChange={handleFileChange}>
        <Button icon={<UploadOutlined />}>Upload File</Button>
      </Upload>
    </RjsfWidgetLayout>
  );
};

FileWidget.propTypes = {
  id: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  required: PropTypes.bool,
};

export { FileWidget };
