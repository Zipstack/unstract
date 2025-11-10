import { UploadOutlined } from "@ant-design/icons";
import { Button, Upload, message } from "antd";
import PropTypes from "prop-types";
import { useState } from "react";

import { RjsfWidgetLayout } from "../../../layouts/rjsf-widget-layout/RjsfWidgetLayout.jsx";

const FileWidget = ({ id, onChange, label, schema, required, readonly }) => {
  const description = schema?.description || "";
  const [selectedFile, setSelectedFile] = useState(null);
  // More precise detection for Oracle wallet files
  const isOracleWallet =
    id === "wallet_file" ||
    (label?.toLowerCase()?.includes("wallet") &&
      (description?.toLowerCase()?.includes("oracle") ||
        description?.toLowerCase()?.includes("zip")));

  const beforeUpload = (file) => {
    // For Oracle wallet files, enforce ZIP format
    if (isOracleWallet) {
      const isZip =
        file.type === "application/zip" ||
        file.type === "application/x-zip-compressed" ||
        file.name.toLowerCase().endsWith(".zip");

      if (!isZip) {
        message.error(
          "Please upload a ZIP file containing your Oracle wallet!"
        );
        return false;
      }

      // Check file size (reasonable limit for wallet files)
      const isLt50M = file.size / 1024 / 1024 < 50;
      if (!isLt50M) {
        message.error("Wallet file must be smaller than 50MB!");
        return false;
      }
    }

    return true;
  };

  const handleFileChange = (info) => {
    const { file } = info;

    if (file.status === "removed") {
      onChange(undefined);
      setSelectedFile(null);
      return;
    }

    // For Oracle wallet files, store the file object directly for connector creation
    if (isOracleWallet && file.originFileObj) {
      onChange(file.originFileObj);
      setSelectedFile(file);
      return;
    }

    // For other file types, handle normal upload flow
    if (file.status === "uploading") {
      message.loading("Uploading file...", 0);
      return;
    }

    if (file.status === "done") {
      message.destroy();
      const response = file.response;

      if (response && response.success) {
        onChange(response.filePath || response.file_path);
        setSelectedFile(file);
        message.success(`${file.name} uploaded successfully!`);
      } else {
        message.error("Upload completed but no file path received");
      }
    } else if (file.status === "error") {
      message.destroy();
      message.error(`${file.name} upload failed. Please try again.`);
    }
  };

  const uploadProps = {
    name: "file",
    // For Oracle wallet files, disable server upload completely
    ...(isOracleWallet
      ? {
          // Disable automatic upload for Oracle wallets
          action: false,
          customRequest: ({ onSuccess }) => {
            // Immediately mark as successful without uploading
            onSuccess("ok");
          },
        }
      : {
          // Normal upload for other file types
          action: "/api/v1/unstract/file_management/file/upload",
          headers: {
            "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")
              ?.value,
          },
          data: {
            // These are required by the file upload API, using dummy values for temporary upload
            connector_id: "00000000-0000-0000-0000-000000000000", // Dummy UUID
            path: "/tmp/wallet_uploads", // Temporary path
          },
        }),
    accept: isOracleWallet ? ".zip" : undefined,
    maxCount: 1,
    beforeUpload: beforeUpload,
    showUploadList: {
      showPreviewIcon: false,
      showRemoveIcon: !readonly,
      showDownloadIcon: false,
    },
  };

  const buttonText = isOracleWallet ? "Upload Wallet ZIP" : "Upload File";
  const displayText = selectedFile
    ? `Selected: ${selectedFile.name}`
    : buttonText;

  return (
    <RjsfWidgetLayout
      label={label}
      description={description}
      required={required}
    >
      <Upload
        id={id}
        onChange={handleFileChange}
        disabled={readonly}
        {...uploadProps}
      >
        <Button icon={<UploadOutlined />} disabled={readonly}>
          {displayText}
        </Button>
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
