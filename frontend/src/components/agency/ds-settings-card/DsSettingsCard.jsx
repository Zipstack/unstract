import {
  ExclamationCircleOutlined,
  ExportOutlined,
  ImportOutlined,
  SettingOutlined,
  CheckCircleTwoTone,
} from "@ant-design/icons";
import {
  Button,
  Col,
  Image,
  Row,
  Select,
  Space,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { getMenuItem, titleCase } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { ConfigureConnectorModal } from "../configure-connector-modal/ConfigureConnectorModal";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DsSettingsCard.css";

const tooltip = {
  input: "Data Source Settings",
  output: "Data Destination Settings",
};

const inputOptions = [
  {
    value: "API",
    label: "API",
  },
  {
    value: "FILESYSTEM",
    label: "File System",
  },
  {
    value: "DATABASE",
    label: "Database",
  },
];

function DsSettingsCard({ type, endpointDetails, message }) {
  const workflowStore = useWorkflowStore();
  const { source, destination, allowChangeEndpoint } = workflowStore;
  const [options, setOptions] = useState({});
  const [openModal, setOpenModal] = useState(false);

  const [listOfConnectors, setListOfConnectors] = useState([]);
  const [filteredList, setFilteredList] = useState([]);

  const [connType, setConnType] = useState(null);

  const [connDetails, setConnDetails] = useState({});
  const [specConfig, setSpecConfig] = useState({});
  const [isSpecConfigLoading, setIsSpecConfigLoading] = useState(false);
  const [formDataConfig, setFormDataConfig] = useState({});
  const [selectedId, setSelectedId] = useState("");
  const { sessionDetails } = useSessionStore();
  const { updateWorkflow } = useWorkflowStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const icons = {
    input: <ImportOutlined className="ds-set-icon-size" />,
    output: <ExportOutlined className="ds-set-icon-size" />,
  };

  useEffect(() => {
    if (type === "output") {
      if (source?.connection_type === "") {
        // Clear options when source is blank
        setOptions({});
      } else {
        // Filter options based on source connection type
        const filteredOptions = ["API"].includes(source?.connection_type)
          ? inputOptions.filter((option) => option.value === "API")
          : inputOptions.filter((option) => option.value !== "API");

        setOptions(filteredOptions);
      }
    }

    if (type === "input") {
      // Remove Database from Source Dropdown
      const filteredOptions = inputOptions.filter(
        (option) => option.value !== "DATABASE"
      );
      setOptions(filteredOptions);
    }
  }, [source, destination]);

  useEffect(() => {
    if (endpointDetails?.connection_type !== connType) {
      setConnType(endpointDetails?.connection_type);
    }

    if (!endpointDetails?.connector_instance?.length) {
      setConnDetails({});
      return;
    }

    if (connDetails?.id === endpointDetails?.connector_instance) {
      return;
    }

    getSourceDetails();
  }, [endpointDetails]);

  useEffect(() => {
    const menuItems = [];
    [...listOfConnectors].forEach((item) => {
      if (
        endpointDetails?.connection_type &&
        item?.connector_mode.split("_").join("") !==
          endpointDetails?.connection_type
      ) {
        return;
      }
      menuItems.push(getMenuItem(item?.name, item?.id, sourceIcon(item?.icon)));
    });
    setSelectedId("");
    setFilteredList(menuItems);

    if (!endpointDetails?.id) {
      return;
    }

    setFormDataConfig(endpointDetails.configuration || {});
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/endpoint/${endpointDetails?.id}/settings/`,
    };

    setIsSpecConfigLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setSpecConfig(data?.schema || {});
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load the spec"));
      })
      .finally(() => {
        setIsSpecConfigLoading(false);
      });
  }, [connType, listOfConnectors]);

  useEffect(() => {
    if (!type) {
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${
        sessionDetails?.orgId
      }/supported_connectors/?type=${type.toUpperCase()}`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setListOfConnectors(data || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {});
  }, [type]);

  const sourceIcon = (src) => {
    return <Image src={src} height={25} width={25} preview={false} />;
  };

  const clearDestination = (updatedData) => {
    const body = { ...destination, ...updatedData };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/endpoint/${destination?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        const updatedData = {};
        updatedData["destination"] = data;
        updateWorkflow(updatedData);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
      });
  };

  const updateDestination = () => {
    // Clear destination dropdown & data when input is switched
    if (type === "input") {
      clearDestination({
        connection_type: "",
        connector_instance: null,
      });
    }
  };

  const handleUpdate = (updatedData, showSuccess) => {
    const body = { ...endpointDetails, ...updatedData };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/endpoint/${endpointDetails?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || {};
        const updatedData = {};
        if (type === "input") {
          updatedData["source"] = data;
        } else {
          updatedData["destination"] = data;
        }
        updateWorkflow(updatedData);
        if (showSuccess) {
          setAlertDetails({
            type: "success",
            content: "Successfully updated",
          });
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to update"));
      });
  };

  const getSourceDetails = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/connector/${endpointDetails?.connector_instance}/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        data["connector_metadata"]["connectorName"] =
          data?.connector_name || "";
        setConnDetails(data);
        setSelectedId(data?.connector_id);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  return (
    <>
      <Row className="ds-set-card-row">
        <Col span={4} className="ds-set-card-col1">
          <Tooltip title={tooltip[type]}>{icons[type]}</Tooltip>
        </Col>
        <Col span={12} className="ds-set-card-col2">
          <SpaceWrapper>
            <Space>
              <Tooltip
                title={
                  !allowChangeEndpoint &&
                  "Workflow used in API/Task/ETL deployment"
                }
              >
                <Select
                  className="ds-set-card-select"
                  size="small"
                  options={options}
                  placeholder="Select Connector Type"
                  value={endpointDetails?.connection_type || undefined}
                  disabled={!allowChangeEndpoint}
                  onChange={(value) => {
                    handleUpdate({
                      connection_type: value,
                      connector_instance: null,
                    });
                    updateDestination();
                  }}
                />
              </Tooltip>

              <Tooltip
                title={`${
                  endpointDetails?.connection_type
                    ? ""
                    : "Select the connector type from the dropdown"
                }`}
              >
                <Button
                  type="text"
                  size="small"
                  onClick={() => setOpenModal(true)}
                  disabled={
                    !endpointDetails?.connection_type || connType === "API"
                  }
                >
                  <SettingOutlined />
                </Button>
              </Tooltip>
            </Space>
            <div className="display-flex-align-center">
              {connDetails?.connector_name ? (
                <Space>
                  <Image
                    src={connDetails?.icon}
                    height={20}
                    width={20}
                    preview={false}
                  />
                  <Typography.Text className="font-size-12">
                    {connDetails?.connector_name}
                  </Typography.Text>
                </Space>
              ) : (
                <>
                  {connType === "API" ? (
                    <Typography.Text
                      className="font-size-12 display-flex-align-center"
                      ellipsis={{ rows: 1, expandable: false }}
                      type="secondary"
                    >
                      <CheckCircleTwoTone twoToneColor="#52c41a" />
                      <span style={{ marginLeft: "5px" }}>
                        {titleCase(type)} set to API successfully
                      </span>
                    </Typography.Text>
                  ) : (
                    <Typography.Text
                      className="font-size-12 display-flex-align-center"
                      ellipsis={{ rows: 1, expandable: false }}
                      type="secondary"
                    >
                      <ExclamationCircleOutlined />
                      <span style={{ marginLeft: "5px" }}>
                        Connector not configured
                      </span>
                    </Typography.Text>
                  )}
                </>
              )}
            </div>
          </SpaceWrapper>
        </Col>
        <Col span={8} className="ds-set-card-col3">
          <Typography.Paragraph
            ellipsis={{ rows: 2, expandable: false }}
            className="font-size-12"
            type="secondary"
          >
            {message}
          </Typography.Paragraph>
        </Col>
      </Row>
      <ConfigureConnectorModal
        open={openModal}
        setOpen={setOpenModal}
        type={type}
        selectedId={selectedId}
        setSelectedId={setSelectedId}
        handleUpdate={handleUpdate}
        filteredList={filteredList}
        connectorMetadata={connDetails?.connector_metadata}
        connectorId={connDetails?.id}
        specConfig={specConfig}
        formDataConfig={formDataConfig}
        setFormDataConfig={setFormDataConfig}
        isSpecConfigLoading={isSpecConfigLoading}
        connDetails={connDetails}
        connType={connType}
      />
    </>
  );
}

DsSettingsCard.propTypes = {
  type: PropTypes.string.isRequired,
  endpointDetails: PropTypes.object.isRequired,
  message: PropTypes.string,
  canUpdate: PropTypes.bool.isRequired,
};

export { DsSettingsCard };
