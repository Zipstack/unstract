import { Form, Input, Modal } from "antd";
import PropTypes from "prop-types";

const { TextArea } = Input;

export function CreateProjectModal({ open, onCancel, onCreate }) {
  const [form] = Form.useForm();

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      await onCreate(values);
      form.resetFields();
    } catch (error) {
      console.error("Validation failed:", error);
    }
  };

  return (
    <Modal
      title="Create Look-Up Project"
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      okText="Create"
      width={600}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          is_active: true,
        }}
      >
        <Form.Item
          name="name"
          label="Project Name"
          rules={[
            { required: true, message: "Please enter a project name" },
            { max: 100, message: "Name must be less than 100 characters" },
          ]}
        >
          <Input placeholder="e.g., Vendor Enrichment" />
        </Form.Item>

        <Form.Item
          name="description"
          label="Description"
          rules={[
            {
              max: 500,
              message: "Description must be less than 500 characters",
            },
          ]}
        >
          <TextArea
            rows={3}
            placeholder="Describe the purpose of this Look-Up project..."
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

CreateProjectModal.propTypes = {
  open: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onCreate: PropTypes.func.isRequired,
};
