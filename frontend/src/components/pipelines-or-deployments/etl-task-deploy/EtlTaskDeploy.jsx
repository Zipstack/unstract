import { Form, Input, Modal, Select, Space, Typography, Button } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { ScheduleOutlined, ClockCircleOutlined } from "@ant-design/icons";
import cronstrue from "cronstrue";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import CronGenerator from "./CronGenerator.jsx";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import "./EtlTaskDeploy.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { useWorkflowStore } from "../../../store/workflow-store.js";
import { getBackendErrorDetail } from "../../../helpers/GetStaticData.js";

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
  const [formDetails, setFormDetails] = useState(
    isEdit ? { ...selectedRow } : { ...defaultFromDetails }
  );
  const [isLoading, setLoading] = useState(false);
  const [openCronGenerator, setOpenCronGenerator] = useState(false);
  const [backendErrors, setBackendErrors] = useState(null);
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    if (workflowId) {
      setFormDetails({ ...formDetails, workflow: workflowId });
    }
  }, [workflowId]);

  useEffect(() => {
    if (formDetails?.cron_string) {
      setSummary(cronstrue.toString(formDetails.cron_string));
    }
  }, [formDetails]);

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

  const clearFormDetails = () => {
    setFormDetails({ ...defaultFromDetails });
  };

  const showCronGenerator = () => {
    setOpenCronGenerator(true);
  };

  const setCronValue = (value) => {
    const updatedValues = { ["cron_string"]: value };
    setFormDetails({ ...formDetails, ...updatedValues });
  };

  const handleCancel = () => {
    setOpen(false);
  };

  const addPipeline = (pipeline) => {
    setTableData((prev) => {
      const prevData = [...prev];
      prevData.push(pipeline);
      return prevData;
    });
  };

  const updatePipeline = () => {
    const body = formDetails;
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
        addPipeline(res?.data);
        setOpen(false);
        clearFormDetails();
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

  const createPipeline = () => {
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
          setDeploymentName(body.pipeline_name);
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
        setAlertDetails(handleException(err, "", setBackendErrors));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  return (
    <>
      <Modal
        title={isEdit ? `Update ${title}` : `Add ${title}`}
        centered
        open={open}
        onOk={isEdit ? updatePipeline : createPipeline}
        onCancel={handleCancel}
        okText={isEdit ? "Update and Deploy" : "Save and Deploy"}
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
            rules={[
              {
                required: true,
                message: "Please add cron schedule",
              },
            ]}
            validateStatus={
              getBackendErrorDetail("cron_string", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("cron_string", backendErrors)}
          >
            <div style={{ display: "flex" }}>
              <Input
                readOnly={true}
                disabled={true}
                value={formDetails?.cron_string}
                style={{ width: "75%" }}
              />
              <Button
                type="primary"
                onClick={showCronGenerator}
                icon={<ScheduleOutlined />}
                className=""
                style={{ marginLeft: "5%", width: "20%" }}
              />
            </div>
          </Form.Item>
          <Space>
            <div
              style={{
                border: "solid 1px #cccccc",
                padding: "4px 8px",
                borderRadius: "5px",
              }}
            >
              <ClockCircleOutlined />
            </div>
            <div>
              <Typography.Text style={{ fontSize: "10px", opacity: 0.6 }}>
                {summary ? summary : "Summary not available."}
              </Typography.Text>
            </div>
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
  setDeploymentName: PropTypes.func,
};
export { EtlTaskDeploy };
