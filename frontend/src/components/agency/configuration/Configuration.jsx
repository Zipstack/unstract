import { Button, Space, Typography } from "antd";
import PropTypes from "prop-types";
import { createRef, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { RjsfFormLayout } from "../../../layouts/rjsf-form-layout/RjsfFormLayout";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import "./Configuration.css";

function Configuration({ setOpen }) {
  const formRef = createRef(null);
  const [schema, setSchema] = useState({});
  const [formData, setFormData] = useState({});
  const [isSchemaLoading, setSchemaLoading] = useState(false);
  const [isUpdateApiLoading, setUpdateApiLoading] = useState(false);
  const { id } = useParams();
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { projectName } = useWorkflowStore();
  const { setAlertDetails } = useAlertStore();

  useEffect(() => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${id}/settings/`,
    };

    setSchemaLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setSchema(data?.schema || {});
        setFormData(data?.settings || {});
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load the form"));
      })
      .finally(() => {
        setSchemaLoading(false);
      });
  }, []);

  const isFormValid = () => {
    if (formRef) {
      formRef?.current?.validateFields((errors, values) => {
        if (errors) {
          return false;
        }
      });
    }
    return true;
  };

  const validateAndSubmit = (updatedFormData) => {
    if (!isFormValid()) {
      return;
    }
    handleSubmit(updatedFormData);
  };

  const handleSubmit = (updatedFormData) => {
    setFormData(updatedFormData);
    const body = {
      workflow_name: projectName,
      settings: updatedFormData,
    };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    setUpdateApiLoading(true);
    axiosPrivate(requestOptions)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Saved successfully",
        });
        setOpen(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to save"));
      })
      .finally(() => {
        setUpdateApiLoading(false);
      });
  };

  return (
    <div>
      <div className="config-head">
        <Typography.Text className="config-head-typo">
          Configuration
        </Typography.Text>
      </div>
      <RjsfFormLayout
        schema={schema}
        formData={formData}
        isLoading={isSchemaLoading}
        validateAndSubmit={validateAndSubmit}
        formRef={formRef}
      >
        <div className="display-flex-right">
          <Space>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <CustomButton
              type="primary"
              htmlType="submit"
              loading={isUpdateApiLoading}
            >
              Save
            </CustomButton>
          </Space>
        </div>
      </RjsfFormLayout>
    </div>
  );
}

Configuration.propTypes = {
  setOpen: PropTypes.func.isRequired,
};

export { Configuration };
