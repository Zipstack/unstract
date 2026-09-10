// Aliased: antd's `Upload` component (still in use until P3) would otherwise be
// shadowed by the lucide icon of the same name.

import { Upload as UploadIcon } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/shims/antd-button";
import { Upload } from "@/components/ui/shims/antd-structure";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const FileWidget = ({ id, onChange, label, schema, required, readonly }) => {
  const description = schema?.description || "";
  const handleFileChange = (info) => {
    if (info.file.status === "done") {
      const fileUrl = info.file.response.url; // Assuming the response contains the uploaded file URL
      onChange(fileUrl);
    }
  };

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      <Upload id={id} onChange={handleFileChange} disabled={readonly}>
        <Button icon={<UploadIcon className="size-4" />}>Upload File</Button>
      </Upload>
    </RjsfWidgetLayout>
  );
};

FileWidget.propTypes = {
  id: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  label: PropTypes.string.isRequired,
  schema: PropTypes.object.isRequired,
  required: PropTypes.bool,
  readonly: PropTypes.bool.isRequired,
};

export { FileWidget };
