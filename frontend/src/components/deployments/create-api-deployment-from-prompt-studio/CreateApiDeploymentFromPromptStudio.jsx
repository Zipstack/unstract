import {
  Form,
  Input,
  Modal,
  Steps,
  Spin,
  Button,
  Typography,
  Space,
  Divider,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
import { RjsfFormLayout } from "../../../layouts/rjsf-form-layout/RjsfFormLayout";
import { workflowService } from "../../workflows/workflow/workflow-service";
import { apiDeploymentsService } from "../api-deployment/api-deployments-service";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import useRequestUrl from "../../../hooks/useRequestUrl";
import "./CreateApiDeploymentFromPromptStudio.css";

const { Step } = Steps;
const { Title, Text } = Typography;

const CreateApiDeploymentFromPromptStudio = ({
  open,
  setOpen,
  toolDetails,
}) => {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const workflowApiService = workflowService();
  const apiDeploymentsApiService = apiDeploymentsService();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { getUrl } = useRequestUrl();
  const navigate = useNavigate();

  const [form] = Form.useForm();
  const [isLoading, setIsLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [backendErrors, setBackendErrors] = useState(null);
  const [toolSchema, setToolSchema] = useState(null);
  const [isSchemaLoading, setIsSchemaLoading] = useState(false);
  const [toolFunctionName, setToolFunctionName] = useState(null);
  const [createdWorkflowId, setCreatedWorkflowId] = useState(null);
  const [createdApiDeployment, setCreatedApiDeployment] = useState(null);
  const [isCreationComplete, setIsCreationComplete] = useState(false);
  const [exportRetryCount, setExportRetryCount] = useState(0);

  // Form data states
  const [deploymentDetails, setDeploymentDetails] = useState({
    display_name: "",
    description: "",
    api_name: "",
  });
  const [toolSettings, setToolSettings] = useState({});

  // Reset form when modal opens
  useEffect(() => {
    if (open && toolDetails) {
      // Generate unique API name with timestamp
      const timestamp = Date.now();
      const baseApiName = toolDetails.tool_name
        .toLowerCase()
        .replace(/\s+/g, "_")
        .substring(0, 15); // Limit base name to 15 chars to leave room for timestamp
      const uniqueApiName = `${baseApiName}_${timestamp}`.substring(0, 30); // Ensure total doesn't exceed 30

      // Set default deployment details based on tool details
      const defaultValues = {
        display_name: `${toolDetails.tool_name} API`,
        description: `API deployment for ${toolDetails.tool_name}`,
        api_name: uniqueApiName,
      };
      setDeploymentDetails(defaultValues);
      form.setFieldsValue(defaultValues);
      setCurrentStep(0);
      setBackendErrors(null);
      setToolSettings({});
      setCreatedWorkflowId(null);
      setCreatedApiDeployment(null);
      setIsCreationComplete(false);
      setExportRetryCount(0);

      // Fetch tool function name first, then schema
      fetchToolFunctionName();
    }
  }, [open, toolDetails, form]);

  const fetchToolFunctionName = async () => {
    if (!toolDetails?.tool_id) return;

    try {
      // Fetch tool list to find the function name for this tool_id
      const response = await axiosPrivate({
        method: "GET",
        url: getUrl("tool/"),
      });

      const tools = response.data || [];
      const matchingTool = tools.find(
        (tool) =>
          tool.function_name === toolDetails.tool_id ||
          tool.name === toolDetails.tool_name
      );

      if (matchingTool?.function_name) {
        setToolFunctionName(matchingTool.function_name);
        // Now fetch schema using the function name
        fetchToolSchema(matchingTool.function_name);
      } else if (exportRetryCount < 2) {
        // Tool not found in registry, automatically export it to the organization
        try {
          await axiosPrivate({
            method: "POST",
            url: getUrl(`prompt-studio/export/${toolDetails.tool_id}`),
            headers: {
              "X-CSRFToken": sessionDetails?.csrfToken,
              "Content-Type": "application/json",
            },
            data: {
              is_shared_with_org: true,
              user_id: [], // Export to everyone in the org
              force_export: true,
            },
          });

          setExportRetryCount((prev) => prev + 1);

          // Retry fetching tool function name after export
          setTimeout(() => {
            fetchToolFunctionName();
          }, 1000); // Wait 1 second for export to complete
        } catch (exportErr) {
          setAlertDetails(handleException(exportErr));
          setToolSchema(null);
        }
      } else {
        setAlertDetails({
          type: "error",
          content: `Tool function name not found in registry for tool: ${toolDetails.tool_id}. Please manually export the tool first.`,
        });
        setToolSchema(null);
      }
    } catch (err) {
      setAlertDetails(handleException(err));
      setToolSchema(null);
    }
  };

  const fetchToolSchema = async (functionName = toolFunctionName) => {
    if (!functionName) {
      setAlertDetails({
        type: "error",
        content: "No function name available for schema fetch",
      });
      setToolSchema(null);
      return;
    }

    setIsSchemaLoading(true);
    try {
      const response = await axiosPrivate({
        method: "GET",
        url: getUrl(`tool_settings_schema/?function_name=${functionName}`),
      });
      setToolSchema(response.data);
    } catch (err) {
      // If tool schema fetch fails, it means the tool doesn't have configurable settings
      // This is common for prompt studio tools that may not be in the tool registry
      setAlertDetails(handleException(err));
      setToolSchema(null);
    } finally {
      setIsSchemaLoading(false);
    }
  };

  const handleDeploymentDetailsChange = (changedValues, allValues) => {
    setDeploymentDetails(allValues);

    // Clear backend errors for the changed field
    const changedFieldName = Object.keys(changedValues)[0];
    if (changedFieldName && backendErrors) {
      const updatedErrors = backendErrors.errors.filter(
        (error) => error.attr !== changedFieldName
      );
      setBackendErrors(
        updatedErrors.length > 0 ? { errors: updatedErrors } : null
      );
    }
  };

  const handleToolSettingsChange = (formData) => {
    setToolSettings(formData);
  };

  const handleCancel = () => {
    setOpen(false);
    setCurrentStep(0);
    setBackendErrors(null);
    setToolSettings({});
    setCreatedWorkflowId(null);
    setCreatedApiDeployment(null);
    setIsCreationComplete(false);
    setExportRetryCount(0);
    form.resetFields();
  };

  const handleNext = () => {
    if (currentStep === 0) {
      // Validate deployment details form
      form
        .validateFields()
        .then((values) => {
          // Update deployment details with the latest form values
          setDeploymentDetails(values);
          setCurrentStep(1);
        })
        .catch(() => {
          // Form validation failed, stay on current step
        });
    }
  };

  const handlePrevious = () => {
    if (currentStep === 1) {
      setCurrentStep(0);
    }
  };

  const cleanupCreatedResources = async (createdResources) => {
    const cleanupPromises = [];
    const cleanupResults = { success: [], failed: [] };

    // Clean up API deployment if created
    if (createdResources.apiDeploymentId) {
      cleanupPromises.push(
        axiosPrivate({
          method: "DELETE",
          url: getUrl(`api_deployment/${createdResources.apiDeploymentId}/`),
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        })
          .then(() => {
            cleanupResults.success.push("API deployment");
          })
          .catch(() => {
            cleanupResults.failed.push("API deployment");
          })
      );
    }

    // Clean up tool instance if created
    if (createdResources.toolInstanceId) {
      cleanupPromises.push(
        axiosPrivate({
          method: "DELETE",
          url: getUrl(`tool_instance/${createdResources.toolInstanceId}/`),
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        })
          .then(() => {
            cleanupResults.success.push("Tool instance");
          })
          .catch(() => {
            cleanupResults.failed.push("Tool instance");
          })
      );
    }

    // Clean up workflow if created
    if (createdResources.workflowId) {
      cleanupPromises.push(
        workflowApiService
          .deleteProject(createdResources.workflowId)
          .then(() => {
            cleanupResults.success.push("Workflow");
          })
          .catch(() => {
            cleanupResults.failed.push("Workflow");
          })
      );
    }

    // Wait for all cleanup operations to complete
    await Promise.allSettled(cleanupPromises);

    // Log cleanup results for debugging
    if (cleanupResults.failed.length > 0) {
      console.warn(
        "Some resources could not be cleaned up:",
        cleanupResults.failed
      );
    }

    return cleanupResults;
  };

  const createApiDeployment = async () => {
    // Prevent duplicate submissions
    if (isLoading) {
      return;
    }

    try {
      setPostHogCustomEvent("intent_create_api_deployment_from_prompt_studio", {
        info: "Creating API deployment from prompt studio",
        tool_id: toolDetails?.tool_id,
        tool_name: toolDetails?.tool_name,
        deployment_name: deploymentDetails.api_name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    setIsLoading(true);
    setBackendErrors(null); // Clear any previous errors

    // Track created resources for cleanup
    const createdResources = {
      workflowId: null,
      toolInstanceId: null,
      apiDeploymentId: null,
    };

    try {
      // Step 1: Export tool
      await axiosPrivate({
        method: "POST",
        url: getUrl(`prompt-studio/export/${toolDetails?.tool_id}`),
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: {
          is_shared_with_org: false,
          user_id: [toolDetails?.created_by],
          force_export: true,
        },
      });

      // Step 2: Create workflow with unique name based on API deployment name
      // Add timestamp to ensure uniqueness even if API name is reused
      const timestamp = Date.now();
      const workflowName = `${deploymentDetails.api_name}_workflow_${timestamp}`;
      const workflowResponse = await workflowApiService.editProject(
        workflowName,
        `Workflow for ${deploymentDetails.display_name} API deployment`,
        null
      );

      const workflowId = workflowResponse.data.id;
      createdResources.workflowId = workflowId;
      setCreatedWorkflowId(workflowId);

      // Step 3: Configure endpoints with API connection type
      await configureApiEndpoints(workflowId);

      // Step 4: Add tool instance to workflow
      const toolInstanceResponse = await axiosPrivate({
        method: "POST",
        url: getUrl("tool_instance/"),
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: {
          tool_id: toolFunctionName || toolDetails.tool_id,
          workflow_id: workflowId,
        },
      });

      createdResources.toolInstanceId = toolInstanceResponse.data.id;

      // Step 5: Update tool instance with proper metadata
      const toolInstanceMetadata = {
        ...toolSettings,
        tool_instance_id:
          toolInstanceResponse?.data?.metadata?.tool_instance_id,
        prompt_registry_id:
          toolInstanceResponse?.data?.metadata?.prompt_registry_id,
        // Use default_llm instead of specific adapter ID for consistency with manual creation
        challenge_llm:
          toolSettings.challenge_llm ||
          toolInstanceResponse.data.metadata.challenge_llm,
      };

      await axiosPrivate({
        method: "PATCH",
        url: getUrl(`tool_instance/${toolInstanceResponse.data.id}/`),
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: {
          metadata: toolInstanceMetadata,
        },
      });

      // Step 6: Create API deployment
      const apiDeploymentResponse =
        await apiDeploymentsApiService.createApiDeployment({
          ...deploymentDetails,
          workflow: workflowId,
        });

      createdResources.apiDeploymentId = apiDeploymentResponse.data.id;
      setCreatedApiDeployment(apiDeploymentResponse.data);
      setIsCreationComplete(true);

      setAlertDetails({
        type: "success",
        content: "API deployment created successfully",
      });
    } catch (err) {
      // Cleanup created resources on failure
      await cleanupCreatedResources(createdResources);

      // Show error message to user
      let errorMessage = "Failed to create API deployment";
      const errorDetails = err?.response?.data?.errors;

      if (errorDetails) {
        setBackendErrors(err.response.data);
        // Extract specific error messages for better user feedback
        if (errorDetails && errorDetails.length > 0) {
          const errorDetails = errorDetails
            .map((e) => `${e.attr}: ${e.detail}`)
            .join(", ");
          errorMessage = `API deployment creation failed: ${errorDetails}`;
        }
      }

      // Always show an alert for API deployment failures
      setAlertDetails({
        type: "error",
        content: errorMessage,
      });

      // If we're on step 2 and have backend errors for deployment fields,
      // go back to step 1 to show the errors
      if (errorDetails && currentStep === 1) {
        const hasDeploymentFieldErrors = errorDetails.some((error) =>
          ["api_name", "display_name", "description"].includes(error?.attr)
        );
        if (hasDeploymentFieldErrors) {
          setCurrentStep(0);
        }
      }
    } finally {
      setIsLoading(false);
    }
  };

  const getModalTitle = () => {
    if (isCreationComplete) {
      return "API Deployment Created Successfully";
    }
    switch (currentStep) {
      case 0:
        return "Create API Deployment - Setup";
      case 1:
        return "Create API Deployment - Tool Settings";
      default:
        return "Create API Deployment";
    }
  };

  const getOkText = () => {
    if (isCreationComplete) {
      return "Close";
    }
    switch (currentStep) {
      case 0:
        return "Next";
      case 1:
        return "Create Deployment";
      default:
        return "Create";
    }
  };

  const configureApiEndpoints = async (workflowId) => {
    // Get existing endpoints for the workflow (they are auto-created)
    const endpointsResponse = await axiosPrivate({
      method: "GET",
      url: getUrl(`workflow/${workflowId}/endpoint/`),
    });

    const endpoints = endpointsResponse.data || [];

    // Update each endpoint to set connection_type to API
    for (const endpoint of endpoints) {
      await axiosPrivate({
        method: "PATCH",
        url: getUrl(`workflow/endpoint/${endpoint.id}/`),
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: {
          connection_type: "API",
          configuration: endpoint.configuration || {},
        },
      });
    }
  };

  const handleOk = () => {
    if (isCreationComplete) {
      handleCancel();
    } else if (currentStep === 0) {
      handleNext();
    } else if (currentStep === 1) {
      createApiDeployment();
    }
  };

  const navigateToWorkflow = () => {
    if (createdWorkflowId) {
      navigate(`/${sessionDetails?.orgName}/workflows/${createdWorkflowId}`);
      handleCancel();
    }
  };

  const navigateToApiDeployments = () => {
    // Navigate to API deployments page with search parameter
    const searchParams = createdApiDeployment?.api_name
      ? `?search=${encodeURIComponent(createdApiDeployment.api_name)}`
      : "";
    navigate(`/${sessionDetails?.orgName}/api${searchParams}`);
    handleCancel();
  };

  const getCancelHandler = () => {
    if (isCreationComplete) {
      return handleCancel;
    }
    return currentStep === 0 ? handleCancel : handlePrevious;
  };

  const getCancelText = () => {
    if (isCreationComplete) {
      return null;
    }
    return currentStep === 0 ? "Cancel" : "Previous";
  };

  const renderToolSettings = () => {
    if (toolSchema) {
      return (
        <RjsfFormLayout
          schema={toolSchema}
          formData={toolSettings}
          setFormData={handleToolSettingsChange}
          isLoading={false}
          validateAndSubmit={() => {}}
          isStateUpdateRequired={true}
        />
      );
    }
    return (
      <p className="no-settings-message">
        No additional settings available for this tool.
      </p>
    );
  };

  return (
    <Modal
      title={getModalTitle()}
      centered
      maskClosable={false}
      open={open}
      onOk={handleOk}
      onCancel={getCancelHandler()}
      okText={getOkText()}
      cancelText={getCancelText()}
      okButtonProps={{
        loading: isLoading,
      }}
      footer={
        isCreationComplete
          ? [
              <Button key="close" onClick={handleCancel}>
                Close
              </Button>,
            ]
          : undefined
      }
      width={700}
      className="create-api-deployment-from-prompt-studio-modal"
    >
      {!isCreationComplete && (
        <div className="steps-container">
          <Steps current={currentStep} size="small">
            <Step title="Deployment Details" />
            <Step title="Tool Settings" />
          </Steps>
        </div>
      )}

      {isCreationComplete && (
        <div className="success-content">
          <Title level={4}>
            🎉 Your API deployment has been created successfully!
          </Title>
          <Space
            direction="vertical"
            size="large"
            className="success-content-space"
          >
            <div>
              <Text strong>API Name:</Text>{" "}
              <Text code>{createdApiDeployment?.api_name}</Text>
            </div>
            <div>
              <Text strong>Display Name:</Text>{" "}
              <Text>{createdApiDeployment?.display_name}</Text>
            </div>
            {createdApiDeployment?.description && (
              <div>
                <Text strong>Description:</Text>{" "}
                <Text>{createdApiDeployment?.description}</Text>
              </div>
            )}

            <Divider />

            <div>
              <Title level={5}>What would you like to do next?</Title>
              <Space
                direction="vertical"
                size="middle"
                className="success-buttons-space"
              >
                <Button
                  type="primary"
                  size="large"
                  onClick={navigateToApiDeployments}
                  className="success-button-full-width"
                >
                  View API Deployment
                </Button>
                <Button
                  size="large"
                  onClick={navigateToWorkflow}
                  className="success-button-full-width"
                >
                  Configure Workflow
                </Button>
              </Space>
            </div>

            <div className="success-footer">
              <Text type="secondary">
                Your API deployment will be available shortly. You can find it
                in the API deployments section.
              </Text>
            </div>
          </Space>
        </div>
      )}

      {!isCreationComplete && currentStep === 0 && (
        <Form
          form={form}
          layout="vertical"
          onValuesChange={handleDeploymentDetailsChange}
          initialValues={deploymentDetails}
        >
          <Form.Item
            label="Display Name"
            name="display_name"
            rules={[
              { required: true, message: "Please enter a display name" },
              {
                max: 30,
                message: "Maximum 30 characters allowed",
              },
            ]}
            validateStatus={
              getBackendErrorDetail("display_name", backendErrors)
                ? "error"
                : ""
            }
            help={getBackendErrorDetail("display_name", backendErrors)}
          >
            <Input.TextArea
              placeholder="Enter display name for the API"
              maxLength={30}
              showCount
              autoSize={{ minRows: 1, maxRows: 2 }}
            />
          </Form.Item>

          <Form.Item
            label="Description"
            name="description"
            validateStatus={
              getBackendErrorDetail("description", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("description", backendErrors)}
          >
            <Input.TextArea
              placeholder="Enter description for the API"
              rows={3}
            />
          </Form.Item>

          <Form.Item
            label="API Name"
            name="api_name"
            rules={[
              { required: true, message: "Please enter an API name" },
              {
                pattern: /^[a-zA-Z0-9_-]+$/,
                message:
                  "Only letters, numbers, hyphen and underscores are allowed",
              },
              {
                max: 30,
                message: "Maximum 30 characters allowed",
              },
            ]}
            validateStatus={
              getBackendErrorDetail("api_name", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("api_name", backendErrors)}
          >
            <Input.TextArea
              placeholder="Enter API name (used in URL)"
              maxLength={30}
              showCount
              autoSize={{ minRows: 1, maxRows: 2 }}
              style={{ resize: "none" }}
            />
          </Form.Item>
        </Form>
      )}

      {!isCreationComplete && currentStep === 1 && (
        <div className="tool-settings-section">
          <h4>Configure Tool Settings</h4>
          {isSchemaLoading ? (
            <div className="loading-container">
              <Spin size="large" />
              <p>Loading tool settings...</p>
            </div>
          ) : (
            renderToolSettings()
          )}
        </div>
      )}
    </Modal>
  );
};

CreateApiDeploymentFromPromptStudio.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  toolDetails: PropTypes.object,
};

export { CreateApiDeploymentFromPromptStudio };
