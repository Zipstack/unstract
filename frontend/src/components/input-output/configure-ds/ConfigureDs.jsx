import { Col, Row } from "antd";
import PropTypes from "prop-types";
import { createRef, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { sourceTypes } from "../../../helpers/GetStaticData.js";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { RjsfFormLayout } from "../../../layouts/rjsf-form-layout/RjsfFormLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { OAuthDs } from "../../oauth-ds/oauth-ds/OAuthDs.jsx";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import "./ConfigureDs.css";

function ConfigureDs({
  spec,
  formData,
  setFormData,
  setOpen,
  oAuthProvider,
  selectedSourceId,
  isLoading,
  addNewItem,
  type,
  editItemId,
  sourceType,
  handleUpdate,
  connDetails,
  metadata,
}) {
  const formRef = createRef(null);
  const axiosPrivate = useAxiosPrivate();
  const [isTcSuccessful, setIsTcSuccessful] = useState(false);
  const [isTcLoading, setIsTcLoading] = useState(false);
  const [isSubmitApiLoading, setIsSubmitApiLoading] = useState(false);
  const [cacheKey, setCacheKey] = useState("");
  const [status, setStatus] = useState("");
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { updateSessionDetails } = useSessionStore();

  const { id } = useParams();

  useEffect(() => {
    if (isTcSuccessful) {
      setIsTcSuccessful(false);
    }
  }, [formData]);

  useEffect(() => {
    const { connector_id: connectorId } = connDetails || {};

    // Check if connectorId matches selectedSourceId and metadata is available
    const shouldSetMetadata = connectorId === selectedSourceId && metadata;
    if (!shouldSetMetadata) return;

    // Set formData based on the condition
    setFormData(metadata);
  }, [selectedSourceId]);

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

  const handleTestConnection = (updatedFormData) => {
    // Check if there any error in form proceed to test connection only there is no error.
    if (!isFormValid()) {
      return;
    }
    if (oAuthProvider?.length && (status !== "success" || !cacheKey?.length)) {
      setAlertDetails({
        type: "error",
        content: "Invalid OAuth",
      });
      return;
    }

    let body = {};
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/`;

    if (sourceType === Object.keys(sourceTypes)[0]) {
      const connectorMetadata = { ...updatedFormData };
      delete connectorMetadata.connectorName;
      body = {
        connector_id: selectedSourceId,
        connector_metadata: connectorMetadata,
      };
      url += "test_connectors/";
    } else {
      const adapterMetadata = { ...updatedFormData };
      delete adapterMetadata.adapterName;
      body = {
        adapter_id: selectedSourceId,
        adapter_metadata: adapterMetadata,
        adapter_type: type.toUpperCase(),
      };
      url += "test_adapters/";
    }

    if (oAuthProvider?.length > 0) {
      body["connector_metadata"] = {
        ...body["connector_metadata"],
        ...{ "oauth-key": cacheKey },
      };
    }

    const requestOptions = {
      method: "POST",
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    setIsTcLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const isValid = res?.data?.is_valid;
        setIsTcSuccessful(isValid);
        if (!isValid) {
          setAlertDetails({
            type: "error",
            content: "Test connection failed",
          });
        } else {
          setAlertDetails({
            type: "success",
            content: "Test connection successful",
          });
        }
      })
      .catch((err) => {
        const TestErrorMessage =
          err?.response?.data?.message || "Test connection failed";
        setAlertDetails(handleException(err, TestErrorMessage));
      })
      .finally(() => {
        setIsTcLoading(false);
      });
  };

  const handleSubmit = () => {
    if (!isTcSuccessful) {
      setAlertDetails({
        type: "error",
        content: "Please test the connection before submitting.",
      });
      return;
    }

    let body = {};
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/`;

    if (sourceType === Object.keys(sourceTypes)[0]) {
      const connectorMetadata = { ...formData };
      const connectorName = connectorMetadata?.connectorName;
      delete connectorMetadata.connectorName;
      body = {
        workflow: id,
        created_by: sessionDetails?.id,
        connector_id: selectedSourceId,
        connector_metadata: connectorMetadata,
        connector_type: type.toUpperCase(),
        connector_name: connectorName,
      };
      url += "connector/";
    } else {
      const adapterMetadata = { ...formData };
      const adapterName = adapterMetadata?.adapter_name;
      delete adapterMetadata.adapter_name;
      body = {
        adapter_id: selectedSourceId,
        adapter_metadata: adapterMetadata,
        adapter_type: type.toUpperCase(),
        adapter_name: adapterName,
      };
      url += "adapter/";
    }

    let method = "POST";
    if (editItemId?.length) {
      method = "PUT";
      url += `${editItemId}/`;
    }

    if (oAuthProvider?.length > 0) {
      const encodedCacheKey = encodeURIComponent(cacheKey);
      url = url + `?oauth-key=${encodedCacheKey}`;
    }

    const requestOptions = {
      method,
      url,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    setIsSubmitApiLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        if (sourceTypes.connectors.includes(type)) {
          handleUpdate({ connector_instance: data?.id });
          return;
        }
        if (data) {
          addNewItem(data, !!editItemId);
        }
        setAlertDetails({
          type: "success",
          content: `Successfully ${
            method === "POST" ? "added" : "updated"
          } connector`,
        });
        if (sourceType === Object.keys(sourceTypes)[1] && method === "POST") {
          updateSession(type);
        }
        setOpen(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsSubmitApiLoading(false);
      });
  };

  const updateSession = (type) => {
    const adapterType = type.toLowerCase();
    const adaptersList = sessionDetails?.adapters;
    if (adaptersList && !adaptersList.includes(adapterType)) {
      adaptersList.push(adapterType);
      const adaptersListInSession = { adapters: adaptersList };
      updateSessionDetails(adaptersListInSession);
    }
  };

  return (
    <div className="config-layout">
      {!isLoading && oAuthProvider?.length > 0 && (
        <OAuthDs
          oAuthProvider={oAuthProvider}
          setCacheKey={setCacheKey}
          setStatus={setStatus}
        />
      )}
      <RjsfFormLayout
        schema={spec}
        formData={formData}
        setFormData={setFormData}
        isLoading={isLoading}
        validateAndSubmit={handleTestConnection}
        formRef={formRef}
        isStateUpdateRequired={true}
      >
        <Row className="config-row">
          <Col span={12} className="config-col1">
            <CustomButton
              block
              type="primary"
              htmlType="submit"
              className="config-tc-btn"
              loading={isTcLoading}
            >
              Test Connection
            </CustomButton>
          </Col>
          <Col span={12} className="config-col2">
            <CustomButton
              block
              type="primary"
              onClick={handleSubmit}
              disabled={!isTcSuccessful}
              loading={isSubmitApiLoading}
            >
              Submit
            </CustomButton>
          </Col>
        </Row>
      </RjsfFormLayout>
    </div>
  );
}

ConfigureDs.propTypes = {
  spec: PropTypes.object,
  formData: PropTypes.object.isRequired,
  setFormData: PropTypes.func.isRequired,
  setOpen: PropTypes.func,
  oAuthProvider: PropTypes.string,
  selectedSourceId: PropTypes.string,
  isLoading: PropTypes.bool.isRequired,
  addNewItem: PropTypes.func,
  type: PropTypes.string,
  editItemId: PropTypes.string,
  sourceType: PropTypes.string.isRequired,
  handleUpdate: PropTypes.func,
  connDetails: PropTypes.object,
  metadata: PropTypes.object,
};

export { ConfigureDs };
