import { Form, Input, Modal, Select } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData.js";
import { useAlertStore } from "../../../store/alert-store";
import { apiDeploymentsService } from "../../deployments/api-deployment/api-deployments-service.js";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { useWorkflowStore } from "../../../store/workflow-store.js";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

const defaultFromDetails = {
  display_name: "",
  description: "",
  api_name: "",
  workflow: "",
};

const CreateApiDeploymentModal = ({
  open,
  setOpen,
  setTableData,
  isEdit,
  selectedRow = {},
  openCodeModal,
  setSelectedRow,
  workflowId,
  workflowEndpointList,
  setDeploymentName,
}) => {
  const workflowStore = useWorkflowStore();
  const { updateWorkflow } = workflowStore;
  const apiDeploymentsApiService = apiDeploymentsService();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { Option } = Select;
  const [formDetails, setFormDetails] = useState(
    isEdit ? { ...selectedRow } : { ...defaultFromDetails }
  );
  const [isLoading, setIsLoading] = useState(false);
  const [form] = Form.useForm();
  const [backendErrors, setBackendErrors] = useState(null);
  const [isFormChanged, setIsFormChanged] = useState(false);
  const { setPostHogCustomEvent } = usePostHogEvents();

  const handleInputChange = (changedValues, allValues) => {
    setIsFormChanged(true);
    setFormDetails({ ...formDetails, ...allValues });
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

  useEffect(() => {
    if (workflowId) {
      setFormDetails((prevState) => ({
        ...prevState,
        workflow: workflowId,
      }));
    }
  }, [workflowId]);

  const clearFormDetails = () => {
    setFormDetails({ ...defaultFromDetails });
  };

  const handleCancel = () => {
    setOpen(false);
  };

  const updateTableData = () => {
    apiDeploymentsApiService
      .getApiDeploymentsList()
      .then((res) => {
        setTableData(res?.data);
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          content: "Error fetching API deployments",
        });
      });
  };

  const createApiDeployment = () => {
    try {
      const wf = workflowEndpointList.find(
        (item) => item?.workflow === formDetails?.workflow
      );
      setPostHogCustomEvent("intent_success_api_deployment", {
        info: "Clicked on 'Save' button",
        deployment_name: formDetails?.api_name,
        workflow_name: wf?.workflow_name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    setIsLoading(true);
    const body = formDetails;
    apiDeploymentsApiService
      .createApiDeployment(body)
      .then((res) => {
        if (workflowId) {
          // Update - can update workflow endpoint status in store
          updateWorkflow({ allowChangeEndpoint: false });
          setDeploymentName(body.display_name);
        } else {
          updateTableData();
          setSelectedRow(res?.data);
          openCodeModal(true);
        }
        setOpen(false);
        clearFormDetails();
        setAlertDetails({
          type: "success",
          content: "New API created successfully",
        });
      })
      .catch((err) => {
        if (err.response?.data) {
          setBackendErrors(err.response.data);

          // Show error notification
          const errorData = err.response.data;
          if (errorData.errors && errorData.errors.length > 0) {
            setAlertDetails({
              type: "error",
              content: errorData.errors[0].detail || "Validation failed",
            });
          }
        } else {
          setAlertDetails(
            handleException(err, "Failed to create API deployment")
          );
        }
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const updateApiDeployment = () => {
    setIsLoading(true);
    const body = formDetails;

    apiDeploymentsApiService
      .updateApiDeployment(body)
      .then((res) => {
        updateTableData();
        setOpen(false);
        clearFormDetails();
        setAlertDetails({
          type: "success",
          content: "API deployment updated successfully",
        });
      })
      .catch((err) => {
        if (err.response?.data) {
          setBackendErrors(err.response.data);
        } else {
          setAlertDetails(
            handleException(err, "Failed to update API deployment")
          );
        }
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  return (
    <Modal
      title={isEdit ? "Update API deployment " : "Add API deployment"}
      centered
      maskClosable={false}
      open={open}
      onOk={isEdit ? updateApiDeployment : createApiDeployment}
      onCancel={handleCancel}
      okText={isEdit ? "Update" : "Save"}
      okButtonProps={{
        loading: isLoading,
        disabled: !isFormChanged,
      }}
      width={450}
    >
      <Form
        form={form}
        name="myForm"
        layout="vertical"
        initialValues={formDetails}
        onValuesChange={handleInputChange}
      >
        <Form.Item
          label="Display Name (for humans)"
          name="display_name"
          rules={[{ required: true, message: "Please enter a display name" }]}
          validateStatus={
            getBackendErrorDetail("display_name", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("display_name", backendErrors)}
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="Description"
          name="description"
          validateStatus={
            getBackendErrorDetail("description", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("description", backendErrors)}
        >
          <Input />
        </Form.Item>

        <Form.Item
          label="API Name (forms part of the API signature)"
          name="api_name"
          rules={[
            { required: true, message: "Please enter an API Name" },
            {
              pattern: /^[a-zA-Z0-9_-]+$/,
              message:
                "Only letters, numbers, hyphen and underscores are allowed",
            },
            {
              pattern: /^.{1,30}$/,
              message: "Maximum 30 characters only allowed",
            },
          ]}
          validateStatus={
            getBackendErrorDetail("api_name", backendErrors) ? "error" : ""
          }
          help={getBackendErrorDetail("api_name", backendErrors)}
        >
          <Input />
        </Form.Item>

        {!workflowId && (
          <Form.Item
            label="Workflow"
            name="workflow"
            rules={[{ required: true, message: "Please select a workflow" }]}
            validateStatus={
              getBackendErrorDetail("workflow", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("workflow", backendErrors)}
          >
            <Select>
              {workflowEndpointList.map((endpoint) => {
                return (
                  <Option
                    value={endpoint.workflow}
                    key={endpoint.workflow_name}
                  >
                    {endpoint.workflow_name}
                  </Option>
                );
              })}
            </Select>
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
};

CreateApiDeploymentModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  setTableData: PropTypes.func,
  isEdit: PropTypes.bool,
  selectedRow: PropTypes.object,
  openCodeModal: PropTypes.func,
  setSelectedRow: PropTypes.func,
  workflowId: PropTypes.string,
  workflowEndpointList: PropTypes.object,
  setDeploymentName: PropTypes.func,
};

export { CreateApiDeploymentModal };
