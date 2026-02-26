import { ArrowLeftOutlined } from "@ant-design/icons";
import { Button, Select, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import "./DefaultTriad.css";
import "../settings/Settings.css";
import usePostHogEvents from "../../../hooks/usePostHogEvents.js";
import { SettingsLayout } from "../settings-layout/SettingsLayout.jsx";

const { Option } = Select;

function DefaultTriad() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const [adapterList, setAdapterList] = useState([]);
  const [dropdownData, setDropdownData] = useState([]);
  const [selectedValues, setSelectedValues] = useState({});
  const [isSubmitEnabled, setIsSubmitEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const desiredOrder = ["LLM", "EMBEDDING", "VECTOR_DB", "X2TEXT"];

  const labelMap = {
    LLM: "Default LLM",
    EMBEDDING: "Default Embedding",
    VECTOR_DB: "Default Vector DB",
    X2TEXT: "Default Text Extractor",
  };

  function getKeyByValue(value) {
    return Object.keys(labelMap).find((key) => labelMap[key] === value);
  }

  // Add current default to the dropdown value
  const updateDropdownData = (defaultValues) => {
    const updatedData = adapterList.map((entry) => {
      if (defaultValues[entry.adapter_type] === entry?.id) {
        return {
          ...entry,
          adapter_name: `${entry.adapter_name} (current default)`,
        };
      }
      return entry;
    });
    // Update the state with the modified data
    setDropdownData(updatedData);
  };

  const fetchData = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setAdapterList(data);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to get the adapters list"),
        );
      });
  };

  const fetchDetaultTriads = () => {
    setIsLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/default_triad/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const defaultAdaptors = res?.data;
        const defaultValues = {};
        defaultValues[getKeyByValue(labelMap.LLM)] =
          defaultAdaptors?.default_llm_adapter;
        defaultValues[getKeyByValue(labelMap.EMBEDDING)] =
          defaultAdaptors?.default_embedding_adapter;
        defaultValues[getKeyByValue(labelMap.VECTOR_DB)] =
          defaultAdaptors?.default_vector_db_adapter;
        defaultValues[getKeyByValue(labelMap.X2TEXT)] =
          defaultAdaptors?.default_x2text_adapter;
        setSelectedValues(defaultValues);
        updateDropdownData(defaultValues);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to fetch Default Triads"));
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (adapterList.length > 0) {
      fetchDetaultTriads();
    }
  }, [adapterList]);

  const handleDropdownChange = (adapterType, selectedValue) => {
    setSelectedValues((prevValues) => ({
      ...prevValues,
      [adapterType]: selectedValue,
    }));
    setIsSubmitEnabled(true);

    try {
      setPostHogCustomEvent("intent_success_select_default_triad", {
        info: "Selected default triad",
        adapter_name: adapterType,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  // Handler for form submission
  const handleSubmit = async () => {
    let body = {
      llm_default: selectedValues[getKeyByValue(labelMap.LLM)],
      embedding_default: selectedValues[getKeyByValue(labelMap.EMBEDDING)],
      vector_db_default: selectedValues[getKeyByValue(labelMap.VECTOR_DB)],
      x2text_default: selectedValues[getKeyByValue(labelMap.X2TEXT)],
    };
    // Filter out null or blank values
    body = Object.fromEntries(
      Object.entries(body).filter(
        ([key, value]) => value !== null && value !== "",
      ),
    );

    const header = {
      "X-CSRFToken": sessionDetails?.csrfToken,
      "Content-Type": "application/json",
    };
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/default_triad/`,
      headers: header,
      data: body,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        fetchData();
        setIsSubmitEnabled(false);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to update Default Triads"),
        );
      });
  };

  return (
    <SettingsLayout>
      <div className="plt-set-head">
        <Button
          size="small"
          type="text"
          onClick={() => navigate(`/${sessionDetails?.orgName}/tools`)}
        >
          <ArrowLeftOutlined />
        </Button>
        <Typography.Text className="plt-set-head-typo">
          Default Triad
        </Typography.Text>
      </div>
      <div className="plt-set-layout">
        <IslandLayout>
          {isLoading ? (
            <SpinnerLoader />
          ) : (
            <div className="plt-set-layout-2 form-width">
              {desiredOrder.map((type) => (
                <SpaceWrapper key={type}>
                  <Typography className="triad-select">
                    {labelMap[type]}
                  </Typography>
                  <Select
                    placeholder={`Select ${labelMap[type]}`}
                    value={selectedValues[type] || undefined}
                    onChange={(value) => handleDropdownChange(type, value)}
                    style={{ width: "100%" }}
                  >
                    {dropdownData
                      .filter((data) => data?.adapter_type === type)
                      .map((data) => (
                        <Option key={data?.id} value={data?.id}>
                          {data?.adapter_name}
                        </Option>
                      ))}
                  </Select>
                </SpaceWrapper>
              ))}
              <CustomButton
                type="primary"
                className="triad-select"
                onClick={handleSubmit}
                disabled={!isSubmitEnabled}
              >
                Save
              </CustomButton>
            </div>
          )}
        </IslandLayout>
      </div>
    </SettingsLayout>
  );
}

export { DefaultTriad };
