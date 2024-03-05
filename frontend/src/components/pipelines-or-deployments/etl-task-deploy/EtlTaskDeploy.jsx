import { InfoCircleOutlined, ScheduleOutlined } from "@ant-design/icons";
import { Input, Modal, Select, Space, Tooltip } from "antd";
import Typography from "antd/es/typography/Typography";
import { isValidCron } from "cron-validator";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import "./EtlTaskDeploy.css";

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
  cron_string: "",
};

const EtlTaskDeploy = ({
  open,
  setOpen,
  type,
  title,
  setTableData,
  workflowId,
}) => {
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const workflowApiService = workflowService();

  const { Option } = Select;
  const [workflowList, setWorkflowList] = useState([]);
  const [formDetails, setFormDetails] = useState({ ...defaultFromDetails });
  const [frequency, setFrequency] = useState("");
  const [summary, setSummary] = useState("");
  const [isGenerateCronLoading, setGenerateCronString] = useState(false);
  const [isSummaryLoading, setSummaryLoading] = useState(false);
  const [isCronStringValid, setCronStringValid] = useState(true);
  const [isLoading, setLoading] = useState(false);

  useEffect(() => {
    if (workflowId) {
      setFormDetails({ ...formDetails, workflow_id: workflowId });
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

  const onChangeHandler = (propertyName, value) => {
    const body = {
      [propertyName]: value,
    };
    setFormDetails({ ...formDetails, ...body });
  };

  useEffect(() => {
    if (open) {
      // Set default value for the form fields
      setRandomFrequency();
    }
  }, [open]);

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

  const setRandomFrequency = () => {
    // Generate a random number between 0 (inclusive) and 7 (exclusive)
    const randomNumber = Math.floor(Math.random() * 7);

    const randomFrequency = `Every ${days[randomNumber]} at 9:00 AM`;
    setFrequency(randomFrequency);
  };

  const clearFormDetails = () => {
    setFrequency("");
    setSummary("");
    setFormDetails({ ...defaultFromDetails });
  };

  const handleCancel = () => {
    setOpen(false);
  };

  const handleGenerateCronString = () => {
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
        if (!workflowId) {
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
        <SpaceWrapper>
          <SpaceWrapper direction="vertical" style={{ width: "100%" }}>
            <Typography>Display Name</Typography>
            <Input
              placeholder="Name"
              name="pipeline_name"
              onChange={(e) => onChangeHandler("pipeline_name", e.target.value)}
              value={formDetails.pipeline_name || ""}
            ></Input>
          </SpaceWrapper>
          {!workflowId && (
            <SpaceWrapper>
              <Typography>Workflow</Typography>
              <Select
                placeholder="select workflow"
                style={{
                  width: "100%",
                }}
                onChange={(value) => onChangeHandler("workflow_id", value)}
                name="workflow_id"
                value={formDetails.workflow_id || ""}
              >
                {workflowList.map((workflow) => {
                  return (
                    <Option value={workflow.id} key={workflow.id}>
                      {workflow.workflow_name}
                    </Option>
                  );
                })}
              </Select>
            </SpaceWrapper>
          )}
          <SpaceWrapper>
            <Typography>
              Frequency of runs
              <Tooltip title="This feature is currently in the experimental phase. Please provide a plain English description of the schedule you have in mind, and I will generate an appropriate Cron schedule for you. You can also directly edit the Cron schedule if it's generated incorrectly.">
                <InfoCircleOutlined
                  style={{ marginLeft: "8px", color: "#5A5A5A" }}
                />
              </Tooltip>
            </Typography>
            <Input.TextArea
              rows={3}
              placeholder="Frequency"
              name="frequency"
              onChange={(e) => setFrequency(e.target.value)}
              value={frequency || ""}
            />
            <div className="display-flex-right">
              <CustomButton
                type="primary"
                onClick={handleGenerateCronString}
                loading={isGenerateCronLoading}
              >
                Generate Cron Schedule
              </CustomButton>
            </div>
          </SpaceWrapper>
          <SpaceWrapper>
            <Typography>Cron Schedule</Typography>
            <Input
              placeholder="Cron Schedule"
              name="cron_string"
              value={formDetails?.cron_string || ""}
              onChange={(e) => onChangeHandler("cron_string", e.target.value)}
              status={isCronStringValid === false && "error"}
            />
          </SpaceWrapper>
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
};
export { EtlTaskDeploy };
