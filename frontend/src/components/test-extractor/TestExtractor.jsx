import { Modal, Upload, Button } from "antd";
import PropTypes from "prop-types";
import { UploadOutlined } from "@ant-design/icons";
import { useState } from "react";

const TestExtractor = ({ open, setOpen }) => {
  const [fileList, setFileList] = useState([]);
  const handleChange = ({ fileList: newFileList }) => setFileList(newFileList);
  const handleCancel = () => {
    setOpen(false);
  };
  const testExecute = () => {
    console.log(fileList);
  };
  // const getRequestBody = (body) => {
  //   const formData = new FormData();
  //   formData.append("files", file);
  //   formData.append("workflow_id", body["workflow_id"]);
  //   formData.append("execution_id", body["execution_id"]);
  //   if (body["execution_action"]) {
  //     formData.append("execution_action", body["execution_action"]);
  //   }
  //   return formData;
  // };
  return (
    <Modal
      title="Upload file to test"
      centered
      open={open}
      maskClosable={false}
      onCancel={handleCancel}
      onOk={testExecute}
      // okButtonProps={{ disabled: fileList.length === 0 }}
      okText="Test"
    >
      <Upload
        fileList={fileList}
        // beforeUpload={beforeUpload}
        // onRemove={onRemove}
        onChange={handleChange}
      >
        <Button icon={<UploadOutlined />}>Select File</Button>
      </Upload>
    </Modal>
  );
};

TestExtractor.propTypes = {
  open: PropTypes.bool,
  setOpen: PropTypes.func.isRequired,
};

export { TestExtractor };
