import { ScheduleOutlined, InfoCircleOutlined } from "@ant-design/icons";
import { Form, Input, Modal, Select, Space, Tooltip } from "antd";
import Typography from "antd/es/typography/Typography";
import { isValidCron } from "cron-validator";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import {
  handleException,
  getBackendErrorDetail,
} from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import "./EtlTaskDeploy.css";
import { useWorkflowStore } from "../../../store/workflow-store.js";

const days = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

const defaultFromDetails = {
  pipeline_name: "",
  workflow_id: "",
  cron_summary: "",
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
}) => {
  const [form] = Form.useForm();
  const workflowStore = useWorkflowStore();
  const { updateWorkflow } = workflowStore;
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const workflowApiService = workflowService();

  const { Option } = Select;
  const [workflowList, setWorkflowList] = useState([]);
  const [formDetails, setFormDetails] = useState(
    isEdit ? { ...selectedRow } : { ...defaultFromDetails }
  );
  const [summary, setSummary] = useState("");
  const [isGenerateCronLoading, setGenerateCronString] = useState(false);
  const [isSummaryLoading, setSummaryLoading] = useState(false);
  const [isCronStringValid, setCronStringValid] = useState(true);
  const [isLoading, setLoading] = useState(false);
  const [backendErrors, setBackendErrors] = useState(null);

  useEffect(() => {
    if (workflowId) {
      setFormDetails({ ...formDetails, workflow_id: workflowId });
    }
  }, [workflowId]);

  useEffect(() => {
    if (isEdit) {
      const cronString = selectedRow?.cron_data?.cron_string;
      const cronSummary = selectedRow?.cron_data?.cron_summary;
      setFormDetails({ ...formDetails, cron_summary: cronSummary });
      setFormDetails({ ...formDetails, cron_string: cronString });
    } else {
      // Generate a random number between 0 (inclusive) and 7 (exclusive)
      const randomNumber = Math.floor(Math.random() * 7);
      const randomFrequency = `Every ${days[randomNumber]} at 9:00 AM`;
      setFormDetails({ ...formDetails, cron_summary: randomFrequency });
    }
  }, [open]);

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

  const getWorkflows = () => {
    const connectorType = type === "task" ? "FILESYSTEM" : "DATABASE";
    workflowApiService
      .getWorkflowEndpointList("DESTINATION", connectorType)
      .then((res) => {
        const updatedData = res?.data.map((record) => ({
          ...record,
          id: record.workflow,
        }));
        setWorkflowList(updatedData);
      })
      .catch(() => {
        console.error("Unable to get workflow list");
      });
  };

  useEffect(() => {
    if (type === "app") {
      getWorkflowList();
    } else {
      getWorkflows();
    }
  }, [type]);

  useEffect(() => {
    const cronString = formDetails?.cron_string || "";
    if (cronString?.length === 0 || isValidCron(cronString)) {
      setCronStringValid(true);
      return;
    }
    setCronStringValid(false);
  }, [formDetails?.cron_string]);

  useEffect(() => {
    const cronString = formDetails?.cron_string || "";
    if (
      isCronStringValid &&
      cronString?.length > 0 &&
      isValidCron(cronString)
    ) {
      handleSummaryGeneration();
    }
  }, [isCronStringValid, formDetails?.cron_string]);

  const clearFormDetails = () => {
    setSummary("");
    setFormDetails({ ...defaultFromDetails });
  };

  const handleCancel = () => {
    setOpen(false);
  };

  const handleGenerateCronString = () => {
    const frequency = formDetails?.frequencyStr;
    if (!frequency) {
      return;
    }

    const body = {
      frequency,
    };
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails.orgId}/cron/generate/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    const newFormDetails = { ...formDetails };

    setGenerateCronString(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        newFormDetails["cron_string"] = data?.cron_string;
      })
      .catch((err) => {
        const msg = "Failed to generate the cron schedule.";
        setAlertDetails(handleException(err, msg));
      })
      .finally(() => {
        setFormDetails({ ...formDetails, ...newFormDetails });
        setGenerateCronString(false);
      });
  };

  const handleSummaryGeneration = () => {
    const cronString = formDetails?.cron_string;
    if (!cronString) {
      return;
    }

    const body = {
      cron_string: cronString,
    };

    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails.orgId}/cron/generate/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    setSummaryLoading(true);
    setSummary("");
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setSummary(data?.summary);
      })
      .catch((err) => {
        const msg = "No data.";
        setAlertDetails(handleException(err, msg));
      })
      .finally(() => {
        setSummaryLoading(false);
      });
  };

  const addPipeline = (pipeline) => {
    setTableData((prev) => {
      const prevData = [...prev];
      prevData.push(pipeline);
      return prevData;
    });
  };

  const createPipeline = () => {
    if (
      !formDetails?.pipeline_name ||
      !formDetails?.workflow_id ||
      !formDetails?.cron_string
    ) {
      setAlertDetails({
        type: "error",
        content: "Please enter all the fields.",
      });
      return;
    }

    if (!isValidCron(formDetails?.cron_string)) {
      setAlertDetails({
        type: "error",
        content: "Invalid cron schedule.",
      });
      return;
    }

    const body = formDetails;
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
        } else {
          addPipeline(res?.data);
        }
        setOpen(false);
        clearFormDetails();
        setAlertDetails({
          type: "success",
          content: "New Pipeline Created Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  return (
    <>
      <Modal
        title={title}
        centered
        open={open}
        onOk={createPipeline}
        onCancel={handleCancel}
        okText="Save and Deploy"
        okButtonProps={{
          loading: isLoading,
        }}
        width={400}
        closable={true}
        maskClosable={false}
      >
        <Form
          form={form}
          name="myForm"
          layout="vertical"
          initialValues={formDetails}
          onValuesChange={handleInputChange}
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
              name="workflow_id"
              rules={[{ required: true, message: "Please select an workflow" }]}
              validateStatus={
                getBackendErrorDetail("workflow_id", backendErrors)
                  ? "error"
                  : ""
              }
              help={getBackendErrorDetail("workflow_id", backendErrors)}
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
            label={
              <div style={{ display: "flex", alignItems: "center" }}>
                <span style={{ marginRight: "8px" }}>Frequency of runs</span>
                <Tooltip title="This feature is currently in the experimental phase. Please provide a plain English description of the schedule you have in mind, and I will generate an appropriate Cron schedule for you. You can also directly edit the Cron schedule if it's generated incorrectly.">
                  <InfoCircleOutlined />
                </Tooltip>
              </div>
            }
            name="cron_summary"
            rules={[{ message: "Please enter frequency" }]}
            validateStatus={
              getBackendErrorDetail("cron_summary", backendErrors)
                ? "error"
                : ""
            }
            help={getBackendErrorDetail("cron_summary", backendErrors)}
          >
            <Input.TextArea
              rows={3}
              style={{ height: 80 }}
              placeholder="Frequency"
            />
          </Form.Item>
          <div className="display-flex-right">
            <CustomButton
              type="primary"
              onClick={handleGenerateCronString}
              loading={isGenerateCronLoading}
            >
              Generate Cron Schedule
            </CustomButton>
          </div>
          <Form.Item
            label="Cron Schedule"
            name="cron_string"
            rules={[
              {
                required: true,
                message: "Please enter/generate cron schedule",
              },
            ]}
            validateStatus={
              getBackendErrorDetail("cron_string", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("cron_string", backendErrors)}
          >
            <Input placeholder="Cron Schedule" />
          </Form.Item>
        </Form>
        <SpaceWrapper>
          <Space>
            <div
              style={{
                border: "solid 1px #cccccc",
                padding: "4px 8px",
                borderRadius: "5px",
              }}
            >
              <ScheduleOutlined />
            </div>
            <div>
              {isSummaryLoading ? (
                <SpinnerLoader />
              ) : (
                <Typography.Text style={{ fontSize: "10px", opacity: 0.6 }}>
                  {isCronStringValid && summary
                    ? summary
                    : "Summary not available."}
                </Typography.Text>
              )}
            </div>
          </Space>
        </SpaceWrapper>
      </Modal>
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
};
export { EtlTaskDeploy };
