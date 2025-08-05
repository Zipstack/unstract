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
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";

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
  selectedSourceName,
  connType,
  formDataConfig,
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
  const {
    posthogTcEventText,
    posthogSubmitEventText,
    posthogConnectorAddedEventText,
    setPostHogCustomEvent,
  } = usePostHogEvents();

  const { id } = useParams();

  // Map connector type to proper role for OAuth isolation
  const connectorRole = type === "input" ? "SOURCE" : "DESTINATION";

  const oauthCacheKey = `oauth-cachekey-${id}-${connectorRole}-${selectedSourceId}`;
  const oauthStatusKey = `oauth-status-${id}-${connectorRole}-${selectedSourceId}`;

  // Initialize OAuth state from localStorage after keys are available
  useEffect(() => {
    if (!oAuthProvider?.length) {
      return;
    }

    // Initialize cache key
    const storedCacheKey = localStorage.getItem(oauthCacheKey);
    if (storedCacheKey) {
      setCacheKey(storedCacheKey);
    }

    // Initialize status from connector-specific key only
    const storedStatus = localStorage.getItem(oauthStatusKey);
    if (storedStatus) {
      setStatus(storedStatus);
    }
  }, [oauthCacheKey, oauthStatusKey, oAuthProvider, selectedSourceId]);

  // Wrapper functions to persist OAuth state to localStorage
  const handleSetCacheKey = (key) => {
    // Only handle OAuth operations for OAuth-enabled connectors
    if (!oAuthProvider?.length) {
      return;
    }
    setCacheKey(key);
    localStorage.setItem(oauthCacheKey, key);
  };

  const handleSetStatus = (newStatus) => {
    // Only handle OAuth operations for OAuth-enabled connectors
    if (!oAuthProvider?.length) {
      return;
    }
    setStatus(newStatus);
    // Store only in connector-specific location to prevent contamination
    localStorage.setItem(oauthStatusKey, newStatus);
  };

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

  // Clear OAuth state when switching to a different connector
  useEffect(() => {
    // Reset test connection success when switching connectors
    setIsTcSuccessful(false);

    // Reset local state only if current connector doesn't have stored OAuth credentials
    const hasStoredOAuthState =
      localStorage.getItem(oauthStatusKey) ||
      localStorage.getItem(oauthCacheKey);
    if (oAuthProvider?.length > 0 && !hasStoredOAuthState) {
      setStatus("");
      setCacheKey("");
    }
  }, [selectedSourceId, id, connectorRole, oauthStatusKey, oauthCacheKey]);

  // Restore OAuth state when returning to a connector with stored credentials
  useEffect(() => {
    if (oAuthProvider?.length > 0) {
      const storedStatus = localStorage.getItem(oauthStatusKey);
      const storedCacheKey = localStorage.getItem(oauthCacheKey);

      // Always restore stored credentials when switching to this connector
      if (storedStatus) {
        setStatus(storedStatus);
      }
      if (storedCacheKey) {
        setCacheKey(storedCacheKey);
      }
    }
  }, [
    selectedSourceId,
    id,
    connectorRole,
    oAuthProvider,
    oauthStatusKey,
    oauthCacheKey,
  ]);

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
        content:
          "OAuth authentication required. Please sign in with Google first.",
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

      try {
        setPostHogCustomEvent(posthogTcEventText[type], {
          info: `Test connection was triggered: ${selectedSourceName}`,
        });
      } catch (err) {
        // If an error occurs while setting custom posthog event, ignore it and continue
      }
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
        connector_id: selectedSourceId,
        connector_metadata: connectorMetadata,
        connector_name: connectorName,
        created_by: sessionDetails?.id,
        workflow: id,
        connector_type: type.toUpperCase(),
      };

      url += "connector/";

      try {
        setPostHogCustomEvent(
          posthogConnectorAddedEventText[`${connType}:${type}`],
          {
            info: `Clicked on 'Submit' button`,
            connector_name: selectedSourceName,
          }
        );
      } catch (err) {
        // If an error occurs while setting custom posthog event, ignore it and continue
      }
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

      try {
        setPostHogCustomEvent(posthogSubmitEventText[type], {
          info: "Clicked on 'Submit' button",
          adpater_name: selectedSourceName,
        });
      } catch (err) {
        // If an error occurs while setting custom posthog event, ignore it and continue
      }
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
          handleUpdate(
            {
              connector_instance_id: data?.id,
              configuration: formDataConfig,
            },
            true
          );
          setIsTcSuccessful(false);
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

        // Keep OAuth state after successful submission for potential re-use
        // OAuth state will be cleared only when switching to different connectors

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
          setCacheKey={handleSetCacheKey}
          setStatus={handleSetStatus}
          selectedSourceId={selectedSourceId}
          workflowId={id}
          connType={connectorRole}
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
  selectedSourceName: PropTypes.string.isRequired,
  connType: PropTypes.string,
  formDataConfig: PropTypes.object,
};

export { ConfigureDs };
