import { Input, Modal, Select } from "antd";
import Typography from "antd/es/typography/Typography";
import PropTypes from "prop-types";
import { useState } from "react";

import { useAlertStore } from "../../../store/alert-store";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";
import { appDeploymentsService } from "../app-deployments/app-deployments-service.js";
import "./AppDeployment.css";

const defaultFromDetails = {
  application_name: "",
  description: "",
  workflow: "",
  template: "",
  subdomain: "",
};

const templateList = [
  {
    id: "CHAT",
    name: "Chat",
  },
  {
    id: "QUESTIONS",
    name: "Canned Questions",
  },
  {
    id: "CHATANDQUESTIONS",
    name: "Chat with Canned Questions",
  },
];

const AppDeployment = ({
  open,
  setOpen,
  setTableData,
  isEdit,
  selectedRow = {},
  setSelectedRow,
  workflowList,
}) => {
  const appDeploymentsApiService = appDeploymentsService();
  const { setAlertDetails } = useAlertStore();

  const { Option } = Select;
  const [formDetails, setFormDetails] = useState(
    isEdit ? { ...selectedRow } : { ...defaultFromDetails }
  );

  const [isLoading, setIsLoading] = useState(false);

  const onChangeHandler = (propertyName, value) => {
    const body = {
      [propertyName]: value,
    };
    setFormDetails({ ...formDetails, ...body });
  };

  const clearFormDetails = () => {
    setFormDetails({ ...defaultFromDetails });
  };

  const handleCancel = () => {
    setOpen(false);
  };

  const validateFormValues = () => {
    if (
      !formDetails?.application_name ||
      !formDetails?.workflow ||
      !formDetails?.description ||
      !formDetails?.subdomain ||
      !formDetails?.template
    ) {
      setAlertDetails({
        type: "error",
        content: "Please enter all the fields.",
      });
      return false;
    }
    return true;
  };

  const updateTableData = () => {
    appDeploymentsApiService
      .getAppDeploymentsList()
      .then((res) => {
        setTableData(res?.data);
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          content: "Error fetching App deployments",
        });
      });
  };

  const createAppDeployment = () => {
    if (validateFormValues()) {
      setIsLoading(true);
      const body = formDetails;
      appDeploymentsApiService
        .createAppDeployment(body)
        .then((res) => {
          updateTableData();
          setSelectedRow(res?.data);
          setOpen(false);
          clearFormDetails();
          setAlertDetails({
            type: "success",
            content: "New App Deployment created successfully",
          });
        })
        .catch((err) => {
          const errorMessage = Object.values(err?.response?.data)[0];
          setAlertDetails({
            type: "error",
            content: errorMessage,
          });
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  };

  const updateAppDeployment = () => {
    if (validateFormValues()) {
      setIsLoading(true);
      const body = formDetails;

      appDeploymentsApiService
        .updateAppDeployment(body)
        .then((res) => {
          updateTableData();
          setOpen(false);
          clearFormDetails();
          setAlertDetails({
            type: "success",
            content: "App deployment updated successfully",
          });
        })
        .catch((err) => {
          const errorMessage = Object.values(err?.response?.data)[0];
          setAlertDetails({
            type: "error",
            content: errorMessage,
          });
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  };

  return (
    <Modal
      title={isEdit ? "Update App deployment " : "Add App deployment"}
      centered
      maskClosable={false}
      open={open}
      onOk={isEdit ? updateAppDeployment : createAppDeployment}
      onCancel={handleCancel}
      okText={isEdit ? "Update" : "Save"}
      okButtonProps={{
        loading: isLoading,
      }}
      width={400}
    >
      <SpaceWrapper>
        <SpaceWrapper direction="vertical">
          <Typography>App Name</Typography>
          <Input
            placeholder="App Name"
            name="application_name"
            onChange={(e) =>
              onChangeHandler("application_name", e.target.value)
            }
            value={formDetails.application_name || ""}
          ></Input>
        </SpaceWrapper>
        <SpaceWrapper direction="vertical">
          <Typography>Description</Typography>
          <Input
            placeholder="Description"
            name="description"
            onChange={(e) => onChangeHandler("description", e.target.value)}
            value={formDetails.description || ""}
          ></Input>
        </SpaceWrapper>
        <SpaceWrapper direction="vertical">
          <Typography>Sub Domain</Typography>
          <Input
            placeholder="Subdomain"
            name="subdomain"
            onChange={(e) => onChangeHandler("subdomain", e.target.value)}
            value={formDetails.subdomain || ""}
          ></Input>
        </SpaceWrapper>
        <SpaceWrapper>
          <Typography>Template</Typography>
          <Select
            placeholder="select template"
            className="template-dropdown"
            onChange={(value) => onChangeHandler("template", value)}
            name="template"
            value={formDetails.template || ""}
          >
            {templateList.map((template) => {
              return (
                <Option value={template.id} key={template.id}>
                  {template.name}
                </Option>
              );
            })}
          </Select>
        </SpaceWrapper>
        <SpaceWrapper>
          <Typography>Workflow</Typography>
          <Select
            placeholder="select workflow"
            className="workflow-dropdown"
            onChange={(value) => onChangeHandler("workflow", value)}
            name="workflow"
            value={formDetails.workflow || ""}
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
      </SpaceWrapper>
    </Modal>
  );
};
AppDeployment.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  setTableData: PropTypes.func,
  isEdit: PropTypes.bool,
  selectedRow: PropTypes.object,
  setSelectedRow: PropTypes.func,
  workflowList: PropTypes.array,
};
export { AppDeployment };
