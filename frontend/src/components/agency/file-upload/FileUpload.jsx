import PropTypes from "prop-types";
import { Modal, Upload, Button } from "antd";
import { UploadOutlined } from "@ant-design/icons";

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
    setFileList([...fileList, file]);
    return false;
  };

  const submitFile = () => {
    continueWfExecution(
      wfExecutionParams[0],
      wfExecutionParams[1],
      wfExecutionParams[2]
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
      >
        <Button icon={<UploadOutlined />}>Select File</Button>
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
