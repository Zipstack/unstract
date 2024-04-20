import { Modal, Upload, Button } from "antd";
import PropTypes from "prop-types";
import { UploadOutlined } from "@ant-design/icons";
import { useState } from "react";

import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store";
import { TextViewerPre } from "../custom-tools/text-viewer-pre/TextViewerPre";

const TestExtractor = ({ open, setOpen, currentItemToTest }) => {
  const [file, setFile] = useState(null);
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const [result, setResult] = useState("");
  const handleChange = (file) => {
    setResult("");
    setFile(file);
  };
  const handleCancel = () => {
    setFile(null);
    setResult("");
    setOpen(false);
  };
  const testExecute = () => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("adapter_id", currentItemToTest.adapter_id);
    const header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "multipart/form-data",
    };
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/try/${currentItemToTest.id}/`,
      headers: header,
      data: formData,
    };

    axiosPrivate(requestOptions).then((res) => {
      setResult(res.data.data);
    });
  };
  return (
    <Modal
      title="Upload file to try"
      centered
      open={open}
      maskClosable={false}
      onCancel={handleCancel}
      onOk={testExecute}
      maxCount={1}
      // okButtonProps={{ disabled: fileList.length === 0 }}
      okText="Try"
    >
      <Upload
        file={file}
        beforeUpload={handleChange}
        multiple={false}
        maxCount={1}
      >
        <Button icon={<UploadOutlined />}>Select File</Button>
      </Upload>
      <TextViewerPre text={result} />
    </Modal>
  );
};

TestExtractor.propTypes = {
  open: PropTypes.bool,
  setOpen: PropTypes.func.isRequired,
  currentItemToTest: PropTypes.object.isRequired,
};

export { TestExtractor };
