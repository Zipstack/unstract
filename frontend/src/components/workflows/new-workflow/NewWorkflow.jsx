import { Form, Input, Modal } from "antd";
import PropTypes from "prop-types";
import { useRef, useState } from "react";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
const { TextArea } = Input;

function NewWorkflow({
  name = "",
  description = "",
  onDone = () => {},
  onClose = () => {},
  loading,
  toggleModal = () => {},
  openModal = {},
  backendErrors,
  setBackendErrors,
}) {
  const [disableCreation, setDisableCreation] = useState(true);
  const nameRef = useRef(name);
  const descriptionRef = useRef(description);
  const [form] = Form.useForm();

  function updateName({ target: { value } }) {
    nameRef.current = value.trim();
    updateCreationStatus();
  }
  function updateDescription({ target: { value } }) {
    descriptionRef.current = value.trim();
    updateCreationStatus();
  }
  function updateCreationStatus() {
    const isNameEmpty = !nameRef.current;
    const isDescriptionEmpty = !descriptionRef.current;
    setDisableCreation(isNameEmpty || isDescriptionEmpty);
  }

  function onCancel() {
    toggleModal(false);
    onClose();
  }

  function onCreate() {
    onDone(nameRef.current, descriptionRef.current);
  }

  const handleInputChange = (changedValues) => {
    const changedFieldName = Object.keys(changedValues)[0];
    form.setFields([
      {
        name: changedFieldName,
        errors: [],
      },
    ]);
    setBackendErrors((prevErrors) => {
      if (prevErrors) {
        const updatedErrors = prevErrors.errors.filter(
          (error) => error.attr !== changedFieldName
        );
        return { ...prevErrors, errors: updatedErrors };
      }
      return null;
    });
  };

  return (
    <Modal
      title={name ? "Edit Workflow" : "New Workflow"}
      open={openModal}
      onCancel={onCancel}
      onOk={onCreate}
      centered
      maskClosable={false}
      okText={name ? "Edit Workflow" : "Create Workflow"}
      width="400px"
      okButtonProps={{ disabled: disableCreation, loading: loading }}
    >
      <Form
        name="workflowForm"
        labelCol={{ span: 8 }}
        wrapperCol={{ span: 16 }}
        onValuesChange={handleInputChange}
      >
        <Form.Item
          label="Workflow Name"
          name="workflow_name"
          rules={[{ required: true, message: "Please enter Workflow name!" }]}
          labelCol={{ span: 24 }}
          wrapperCol={{ span: 24 }}
          validateStatus={
            getBackendErrorDetail("workflow_name", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("workflow_name", backendErrors)}
        >
          <Input defaultValue={nameRef.current} onChange={updateName} />
        </Form.Item>
        <Form.Item
          label="Description"
          name="workflow_description"
          rules={[{ required: true, message: "Please enter Description!" }]}
          labelCol={{ span: 24 }}
          wrapperCol={{ span: 24 }}
          validateStatus={
            getBackendErrorDetail("workflow_description", backendErrors)
              ? "error"
              : ""
          }
          help={getBackendErrorDetail("workflow_description", backendErrors)}
        >
          <TextArea
            defaultValue={descriptionRef.current}
            autoSize={{ minRows: 4, maxRows: 6 }}
            onChange={updateDescription}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

NewWorkflow.propTypes = {
  name: PropTypes.string,
  description: PropTypes.string,
  loading: PropTypes.bool,
  onDone: PropTypes.func,
  onClose: PropTypes.func,
  openModal: PropTypes.bool,
  toggleModal: PropTypes.func,
  setBackendErrors: PropTypes.func,
  backendErrors: PropTypes.object,
};

export { NewWorkflow };
