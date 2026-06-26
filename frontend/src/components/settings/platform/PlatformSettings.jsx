import {
  ArrowLeftOutlined,
  CopyOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import {
  Button,
  Col,
  Divider,
  Input,
  InputNumber,
  Row,
  Tag,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal.jsx";
import "./PlatformSettings.css";
import "../settings/Settings.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import { SettingsLayout } from "../settings-layout/SettingsLayout.jsx";

const defaultKeys = [
  {
    id: null,
    keyName: "Key #1",
    key: "",
    isActive: true,
  },
  {
    id: null,
    keyName: "Key #2",
    key: "",
    isActive: false,
  },
];

// Keyboard-accessible "Inactive" pill. Split out of the key-row render so the
// activation control's conditional handlers don't inflate the row's complexity.
function InactivePlatformKeyTag({ keyName, canActivate, onActivate }) {
  if (!canActivate) {
    return <Tag tabIndex={-1}>Inactive</Tag>;
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onActivate();
    }
  };

  return (
    <Tag
      className="plt-set-key-pill-clickable"
      role="button"
      tabIndex={0}
      aria-label={`Activate ${keyName}`}
      onClick={onActivate}
      onKeyDown={handleKeyDown}
    >
      Inactive
    </Tag>
  );
}

InactivePlatformKeyTag.propTypes = {
  keyName: PropTypes.string,
  canActivate: PropTypes.bool,
  onActivate: PropTypes.func.isRequired,
};

function PlatformSettings() {
  const [activeKey, setActiveKey] = useState(null);
  const [keys, setKeys] = useState(defaultKeys);
  const [isLoadingIndex, setLoadingIndex] = useState(null);
  const [isDeletingIndex, setDeletingIndex] = useState(null);
  // UI shows minutes; wire format (and ConfigSpec.value) is seconds.
  const [batchIntervalMinutes, setBatchIntervalMinutes] = useState(null);
  const [isSavingInterval, setIsSavingInterval] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();

  useEffect(() => {
    // Wait for session hydration — without this guard the first render
    // fires GET against /api/v1/unstract/undefined/... and silently 404s.
    if (!sessionDetails?.orgId) {
      return;
    }
    // Load org-scoped batch interval. Falls back to null on failure (logged
    // in the catch below) so the rest of the page still renders.
    axiosPrivate({
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/notifications/settings/`,
    })
      .then((res) => {
        const seconds = res?.data?.club_interval_seconds;
        if (typeof seconds === "number" && seconds > 0) {
          setBatchIntervalMinutes(Math.round(seconds / 60));
        }
      })
      .catch((err) => {
        // Non-fatal for page render, but log it: a failed load otherwise
        // looks identical to "no override set" (the field stays blank), so
        // the admin could edit from a wrong baseline and overwrite the real
        // value on save.
        console.warn("Failed to load notification batch interval", err);
      });
  }, [sessionDetails?.orgId]);

  const handleSaveInterval = () => {
    if (
      !batchIntervalMinutes ||
      batchIntervalMinutes < 1 ||
      batchIntervalMinutes > 120
    ) {
      setAlertDetails({
        type: "error",
        content: "Notification interval must be between 1 and 120 minutes.",
      });
      return;
    }
    setIsSavingInterval(true);
    axiosPrivate({
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/notifications/settings/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: { club_interval_seconds: batchIntervalMinutes * 60 },
    })
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Notification batch interval updated.",
        });
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to update batch interval"),
        );
      })
      .finally(() => {
        setIsSavingInterval(false);
      });
  };

  useEffect(() => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/platform/keys/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        if (data?.length === 0) {
          return;
        }

        const newKeys = keys.map((key, keyIndex) => {
          const keyName = key?.keyName;
          const keyDetails = data.find((item) => item?.key_name === keyName);

          if (keyDetails) {
            if (keyDetails?.is_active === true) {
              setActiveKey(keyIndex);
            }
            return {
              id: keyDetails?.id,
              keyName: keyDetails?.key_name,
              key: keyDetails?.key,
              isActive: keyDetails?.is_active,
            };
          } else {
            return {
              id: null,
              keyName: "Key #" + (keyIndex + 1),
              key: "",
              isActive: false,
            };
          }
        });

        if (newKeys?.length === 1) {
          newKeys.push({
            id: null,
            keyName: "Key #2",
            key: "",
            isActive: false,
          });
        }

        setKeys(newKeys);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to get the keys"));
      });
  }, []);

  const handleGenerate = (index) => {
    const details = { ...keys[index] };

    const body = {
      key_name: details?.keyName,
    };

    const url = `/api/v1/unstract/${sessionDetails?.orgId}/platform/keys/`;
    let method = "POST";
    if (details?.id?.length > 0) {
      // url += "/refresh";
      body["id"] = details.id;
      method = "PUT";
    } else {
      // url += "/generate";
      body["is_active"] = activeKey === index;
    }

    try {
      if (details?.id?.length > 0) {
        setPostHogCustomEvent("intent_api_key_refreshed", {
          info: "API Key has been refreshed",
        });
      } else {
        setPostHogCustomEvent("intent_api_key_generation", {
          info: "API Key has been generated",
        });
      }
    } catch (_err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    const requestOptions = {
      method,
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    setLoadingIndex(index);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const newKeys = [...keys];
        newKeys[index].id = data?.id || null;
        newKeys[index].key = data?.key || null;
        setKeys(newKeys);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate the key"));
      })
      .finally(() => {
        setLoadingIndex(null);
      });
  };

  const handleDelete = (index) => {
    const keyDetails = { ...keys[index] };

    if (keyDetails?.id === null) {
      return;
    }

    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/platform/keys/${keyDetails?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    setDeletingIndex(index);
    axiosPrivate(requestOptions)
      .then(() => {
        const newKeys = [...keys];
        newKeys[index].id = null;
        newKeys[index].key = "";
        setKeys(newKeys);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to delete"));
      })
      .finally(() => {
        setDeletingIndex(null);
      });
  };

  const handleToggle = (index) => {
    const prevActiveKey = activeKey;
    setActiveKey(index);

    const keyDetails = { ...keys[index] };
    if (keyDetails?.id === null) {
      return;
    }

    const body = {
      action: "ACTIVATE",
    };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/platform/keys/${keyDetails?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions).catch((err) => {
      setActiveKey(prevActiveKey);
      setAlertDetails(handleException(err, "Failed to set active key"));
    });
  };

  const copyText = (text) => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Key copied to clipboard",
        });
      })
      .catch((error) => {
        setAlertDetails({
          type: "error",
          content: "Copy failed",
        });
      });
  };

  return (
    <SettingsLayout>
      <div>
        <div className="plt-set-head">
          <Button
            size="small"
            type="text"
            onClick={() => navigate(`/${sessionDetails?.orgName}/tools`)}
          >
            <ArrowLeftOutlined />
          </Button>
          <Typography.Text className="plt-set-head-typo">
            Platform Settings
          </Typography.Text>
        </div>
        <div className="plt-set-layout">
          <IslandLayout>
            <div className="plt-set-layout-2">
              <div className="plt-set-section">
                <Typography.Title level={5}>Internal API Keys</Typography.Title>
                <Typography.Text
                  type="secondary"
                  className="plt-set-section-subtitle"
                >
                  Authenticate platform-to-platform requests. Keep these values
                  secret.
                </Typography.Text>
                <div className="plt-set-inner-card">
                  {keys.map((keyDetails, keyIndex) => {
                    const isActive =
                      Boolean(keyDetails?.id) && activeKey === keyIndex;
                    const canActivate = keyDetails?.id !== null;
                    return (
                      <div key={keyDetails?.keyName}>
                        <div>
                          <div className="plt-set-key-head">
                            <Typography.Text>
                              {keyDetails?.keyName}
                            </Typography.Text>
                            {isActive ? (
                              <Tag color="success">Active</Tag>
                            ) : (
                              <InactivePlatformKeyTag
                                keyName={keyDetails?.keyName}
                                canActivate={canActivate}
                                onActivate={() => handleToggle(keyIndex)}
                              />
                            )}
                          </div>
                          <div>
                            <Row gutter={10}>
                              <Col>
                                <div className="plt-set-key-display">
                                  <Input
                                    size="small"
                                    value={keys[keyIndex].key}
                                    suffix={
                                      <CopyOutlined
                                        onClick={() =>
                                          copyText(keys[keyIndex].key)
                                        }
                                      />
                                    }
                                  />
                                </div>
                              </Col>
                              <Col>
                                <Button
                                  size="small"
                                  loading={isLoadingIndex === keyIndex}
                                  onClick={() => handleGenerate(keyIndex)}
                                >
                                  {keyDetails?.id?.length > 0
                                    ? "Refresh"
                                    : "Generate"}
                                </Button>
                              </Col>
                              <Col>
                                <ConfirmModal
                                  handleConfirm={() => handleDelete(keyIndex)}
                                  content="Want to delete this platform key? This action cannot be undone."
                                  okText="Delete"
                                >
                                  <Button
                                    size="small"
                                    icon={<DeleteOutlined />}
                                    disabled={keyDetails?.id === null}
                                    loading={isDeletingIndex === keyIndex}
                                  />
                                </ConfirmModal>
                              </Col>
                            </Row>
                          </div>
                        </div>
                        {keyIndex < keys?.length - 1 && <Divider />}
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="plt-set-section">
                <Typography.Title level={5}>Notifications</Typography.Title>
                <Typography.Text
                  type="secondary"
                  className="plt-set-section-subtitle"
                >
                  Control how often the platform notifies you about activity.
                </Typography.Text>
                <div className="plt-set-inner-card">
                  <Typography.Text className="plt-set-notif-field-label">
                    Notification interval
                  </Typography.Text>
                  <div className="plt-set-notif-field-row">
                    <InputNumber
                      min={1}
                      max={120}
                      step={1}
                      precision={0}
                      value={batchIntervalMinutes}
                      onChange={(v) => setBatchIntervalMinutes(v)}
                    />
                    <Button
                      type="primary"
                      onClick={handleSaveInterval}
                      loading={isSavingInterval}
                    >
                      Save
                    </Button>
                  </div>
                  <Typography.Text
                    type="secondary"
                    className="plt-set-notif-helper"
                  >
                    Allowed: 1 to 120 minutes. Default: 5 minutes.
                  </Typography.Text>
                </div>
              </div>
            </div>
          </IslandLayout>
        </div>
      </div>
    </SettingsLayout>
  );
}

export { PlatformSettings };
