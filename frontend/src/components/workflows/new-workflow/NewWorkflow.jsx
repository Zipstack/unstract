import { Form, Input, Modal } from "antd";
import PropTypes from "prop-types";
import { useRef, useState } from "react";
const { TextArea } = Input;

function NewWorkflow({
  name = "",
  description = "",
  onDone = () => {},
  onClose = () => {},
  loading = {},
  toggleModal = () => {},
  openModal = {},
}) {
  const [disableCreation, setDisableCreation] = useState(true);
  const nameRef = useRef(name);
  const descriptionRef = useRef(description);

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
      >
        <Form.Item
          label="Workflow Name"
          name="Workflow Name"
          rules={[{ required: true, message: "Please enter Workflow name!" }]}
          labelCol={{ span: 24 }}
          wrapperCol={{ span: 24 }}
        >
          <Input defaultValue={nameRef.current} onChange={updateName} />
        </Form.Item>
        <Form.Item
          label="Description"
          name="Description"
          rules={[{ required: true, message: "Please enter Description!" }]}
          labelCol={{ span: 24 }}
          wrapperCol={{ span: 24 }}
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
};

export { NewWorkflow };
