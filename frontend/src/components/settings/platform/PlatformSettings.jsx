import {
  ArrowLeftOutlined,
  CopyOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { Button, Col, Divider, Input, Radio, Row, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal.jsx";
import "./PlatformSettings.css";
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

function PlatformSettings() {
  const [activeKey, setActiveKey] = useState(null);
  const [keys, setKeys] = useState(defaultKeys);
  const [isLoadingIndex, setLoadingIndex] = useState(null);
  const [isDeletingIndex, setDeletingIndex] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();

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
    } catch (err) {
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
    <SettingsLayout activeKey="platform">
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
              <div>
                {keys.map((keyDetails, keyIndex) => {
                  return (
                    <div key={keyDetails?.keyName}>
                      <div>
                        <div className="plt-set-key-head">
                          <Row>
                            <Col>
                              <div className="plt-set-key-head-col-1">
                                <Typography.Text>
                                  {keyDetails?.keyName}
                                </Typography.Text>
                              </div>
                            </Col>
                            <Col>
                              <div className="plt-set-key-head-col-2">
                                <Radio
                                  checked={
                                    keyDetails?.id && activeKey === keyIndex
                                  }
                                  disabled={keyDetails?.id === null}
                                  onClick={() => handleToggle(keyIndex)}
                                >
                                  Active Key
                                </Radio>
                              </div>
                            </Col>
                          </Row>
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
                                  disabled={keyDetails?.id === null}
                                  loading={isDeletingIndex === keyIndex}
                                >
                                  <DeleteOutlined />
                                </Button>
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
          </IslandLayout>
        </div>
      </div>
    </SettingsLayout>
  );
}

export { PlatformSettings };
