// Aliased: antd's `Upload` component (still in use until P3) would otherwise be
// shadowed by the lucide icon of the same name.

import { Upload as UploadIcon } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/shims/antd-button";
import { Modal } from "@/components/ui/shims/antd-overlays";
import { Upload } from "@/components/ui/shims/antd-structure";
import { message } from "@/hooks/useAppToast";
import {
  WORKFLOW_PAGE_MAX_FILES,
  WORKFLOW_VALIDATION_MESSAGES,
} from "./WfConstants.js";

const FileUpload = ({
  open,
  setOpen,
  fileList,
  setFileList,
  wfExecutionParams,
  continueWfExecution,
}) => {
  const onRemove = (file) => {
    setFileList(fileList.filter((item) => item.uid !== file.uid));
  };

  const beforeUpload = (file) => {
    if (fileList.length >= WORKFLOW_PAGE_MAX_FILES) {
      message.error(WORKFLOW_VALIDATION_MESSAGES.MAX_FILES_EXCEEDED);
      return false;
    }
    setFileList([...fileList, file]);
    return false;
  };

  const submitFile = () => {
    if (fileList.length === 0) {
      message.error(WORKFLOW_VALIDATION_MESSAGES.NO_FILES_SELECTED);
      return;
    }
    if (fileList.length > WORKFLOW_PAGE_MAX_FILES) {
      message.error(WORKFLOW_VALIDATION_MESSAGES.MAX_FILES_EXCEEDED);
      return;
    }
    continueWfExecution(
      wfExecutionParams[0],
      wfExecutionParams[1],
      wfExecutionParams[2],
    );
    setOpen(false);
  };

  const handleCancel = () => {
    setOpen(false);
  };

  return (
    <Modal
      title="Upload input file"
      centered
      open={open}
      maskClosable={false}
      onCancel={handleCancel}
      onOk={submitFile}
      okButtonProps={{ disabled: fileList.length === 0 }}
      okText="Continue"
    >
      <Upload
        fileList={fileList}
        beforeUpload={beforeUpload}
        onRemove={onRemove}
        maxCount={WORKFLOW_PAGE_MAX_FILES}
        multiple={true}
      >
        <Button icon={<UploadIcon className="size-4" />}>Select File</Button>
      </Upload>
    </Modal>
  );
};

FileUpload.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  fileList: PropTypes.array.isRequired,
  setFileList: PropTypes.func.isRequired,
  wfExecutionParams: PropTypes.array.isRequired,
  continueWfExecution: PropTypes.func.isRequired,
};
export default FileUpload;
