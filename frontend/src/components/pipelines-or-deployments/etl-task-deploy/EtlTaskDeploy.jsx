import { Form, Input, Modal, Select, Space, Typography, Button } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { ScheduleOutlined, ClockCircleOutlined } from "@ant-design/icons";
import cronstrue from "cronstrue";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import CronGenerator from "../../cron-generator/CronGenerator.jsx";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import "./EtlTaskDeploy.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { useWorkflowStore } from "../../../store/workflow-store.js";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData.js";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

const defaultFromDetails = {
  pipeline_name: "",
  workflow: "",
  cron_string: "",
};

const EtlTaskDeploy = ({
  open,
  setOpen,
  type,
  title,
  setTableData,
  workflowId,
  isEdit,
  selectedRow = {},
  setSelectedRow,
  setDeploymentName,
}) => {
  const [form] = Form.useForm();
  const workflowStore = useWorkflowStore();
  const { updateWorkflow } = workflowStore;
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const workflowApiService = workflowService();
  const handleException = useExceptionHandler();

  const { Option } = Select;
  const [workflowList, setWorkflowList] = useState([]);
  const [formDetails, setFormDetails] = useState({});
  const [isLoading, setLoading] = useState(false);
  const [openCronGenerator, setOpenCronGenerator] = useState(false);
  const [backendErrors, setBackendErrors] = useState(null);
  const [summary, setSummary] = useState(null);
  const { posthogDeploymentEventText, setPostHogCustomEvent } =
    usePostHogEvents();

  useEffect(() => {
    console.log(selectedRow);
    if (isEdit) {
      setFormDetails(selectedRow);
      handleSummary(selectedRow?.cron_string);
    } else {
      setFormDetails(defaultFromDetails);
      handleSummary(null);
    }
  }, []);

  useEffect(() => {
    form.resetFields();
  }, [formDetails]);

  useEffect(() => {
    if (workflowId) {
      setFormDetails({ ...formDetails, workflow: workflowId });
    }
  }, [workflowId]);

  const getWorkflowList = () => {
    workflowApiService
      .getWorkflowList()
      .then((res) => {
        setWorkflowList(res?.data);
      })
      .catch(() => {
        console.error("Unable to get workflow list");
      });
  };

  const handleInputChange = (changedValues, allValues) => {
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
  const fetchWorkflows = (type) =>
    workflowApiService
      .getWorkflowEndpointList("DESTINATION", type)
      .then((res) =>
        res?.data.map((record) => ({
          ...record,
          id: record.workflow,
        }))
      )
      .catch(() => {
        return [];
      });
  const getWorkflows = () => {
    const connectorType = type === "task" ? "FILESYSTEM" : "DATABASE";
    setWorkflowList([]);
    fetchWorkflows(connectorType).then((data) => {
      if (connectorType === "DATABASE") {
        fetchWorkflows("MANUALREVIEW").then((manualReviewData) => {
          const combinedData = [...data, ...manualReviewData];
          setWorkflowList(combinedData);
        });
      } else {
        setWorkflowList(data);
      }
    });
  };

  useEffect(() => {
    if (type === "app") {
      getWorkflowList();
    } else {
      getWorkflows();
    }
  }, [type]);

  const showCronGenerator = () => {
    setOpenCronGenerator(true);
  };

  const setCronValue = (value) => {
    const updatedValues = { ["cron_string"]: value };
    setFormDetails({ ...formDetails, ...updatedValues });
    handleSummary(value);
  };

  const handleSummary = (cronString) => {
    if (!cronString) {
      setSummary(null);
      return;
    }
    setSummary(cronstrue.toString(cronString));
  };

  const addPipeline = (pipeline) => {
    setTableData((prev) => {
      const prevData = [...prev];
      prevData.push(pipeline);
      return prevData;
    });
  };

  const updatePipelineTable = (pipeline) => {
    setTableData((prev) => {
      const index = prev.findIndex((item) => item?.id === pipeline?.id);
      if (index === -1) return prev;

      const newData = [...prev];
      newData[index] = { ...newData[index], ...pipeline };
      return newData;
    });
  };

  const updatePipeline = (formValues) => {
    const body = { ...formDetails, ...formValues };
    body["pipeline_type"] = type.toUpperCase();

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/${body?.id}/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };
    setLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        updatePipelineTable(data);
        setSelectedRow(data);
        setOpen(false);
        setAlertDetails({
          type: "success",
          content: "Pipeline Updated Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "", setBackendErrors));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const createPipeline = (formValues) => {
    try {
      const wf = workflowList.find((item) => item?.id === formValues?.workflow);
      setPostHogCustomEvent(posthogDeploymentEventText[`${type}_success`], {
        info: "Clicked on 'Save and Deploy' button",
        deployment_name: formValues?.pipeline_name,
        workflow_name: wf?.workflow_name,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    const body = { ...formDetails, ...formValues };
    body["pipeline_type"] = type.toUpperCase();

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/pipeline/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    setLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        if (workflowId) {
          // Update - can update workflow endpoint status in store
          updateWorkflow({ allowChangeEndpoint: false });
          setDeploymentName(body.pipeline_name);
        } else {
          addPipeline(res?.data);
        }
        setOpen(false);
        setAlertDetails({
          type: "success",
          content: "New Pipeline Created Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "", setBackendErrors));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const handleSubmit = (formValues) => {
    if (isEdit) {
      updatePipeline(formValues);
    } else {
      createPipeline(formValues);
    }
  };

  return (
    <>
      <Modal
        title={isEdit ? `Update ${title}` : `Add ${title}`}
        centered
        open={open}
        width={400}
        closable={true}
        maskClosable={false}
        footer={null}
        onCancel={() => setOpen(false)}
      >
        <Form
          form={form}
          name="myForm"
          layout="vertical"
          initialValues={formDetails}
          onValuesChange={handleInputChange}
          onFinish={handleSubmit}
        >
          <Form.Item
            label="Display Name"
            name="pipeline_name"
            rules={[{ required: true, message: "Please enter display name" }]}
            validateStatus={
              getBackendErrorDetail("pipeline_name", backendErrors)
                ? "error"
                : ""
            }
            help={getBackendErrorDetail("pipeline_name", backendErrors)}
          >
            <Input placeholder="Name" />
          </Form.Item>

          {!workflowId && (
            <Form.Item
              label="Workflow"
              name="workflow"
              rules={[{ required: true, message: "Please select an workflow" }]}
              validateStatus={
                getBackendErrorDetail("workflow", backendErrors) ? "error" : ""
              }
              help={getBackendErrorDetail("workflow", backendErrors)}
            >
              <Select>
                {workflowList.map((workflow) => {
                  return (
                    <Option value={workflow.id} key={workflow.workflow_name}>
                      {workflow.workflow_name}
                    </Option>
                  );
                })}
              </Select>
            </Form.Item>
          )}
          <Form.Item
            label="Cron Schedule"
            name="cron_string"
            validateStatus={
              getBackendErrorDetail("cron_string", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("cron_string", backendErrors)}
          >
            <div className="cron-string-div">
              <Input
                readOnly={true}
                value={formDetails?.cron_string}
                className="cron-string-input"
              />
              <Button
                type="primary"
                onClick={showCronGenerator}
                icon={<ScheduleOutlined />}
                className="cron-string-btn"
              />
            </div>
          </Form.Item>
          <Space>
            <div className="cron-summary-div">
              <ClockCircleOutlined />
            </div>
            <div>
              <Typography.Text className="summary-text">
                {summary || "Summary not available."}
              </Typography.Text>
            </div>
          </Space>
          <Space className="display-flex-right">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="primary" loading={isLoading} htmlType="submit">
              {isEdit ? "Update and Deploy" : "Save and Deploy"}
            </Button>
          </Space>
        </Form>
      </Modal>
      {openCronGenerator && (
        <CronGenerator
          open={openCronGenerator}
          showCronGenerator={setOpenCronGenerator}
          setCronValue={setCronValue}
        />
      )}
    </>
  );
};

EtlTaskDeploy.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  title: PropTypes.string.isRequired,
  setTableData: PropTypes.func,
  workflowId: PropTypes.string,
  isEdit: PropTypes.bool,
  selectedRow: PropTypes.object,
  setSelectedRow: PropTypes.func,
  setDeploymentName: PropTypes.func,
};

export { EtlTaskDeploy };
