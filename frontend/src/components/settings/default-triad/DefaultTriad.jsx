import { ArrowLeftOutlined } from "@ant-design/icons";
import { Button, Select, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper.jsx";
import "./DefaultTriad.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";

const { Option } = Select;

function DefaultTriad() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const [dropdownData, setDropdownData] = useState([]);
  const [selectedValues, setSelectedValues] = useState({});
  const [isSubmitEnabled, setIsSubmitEnabled] = useState(false);

  const desiredOrder = ["LLM", "EMBEDDING", "VECTOR_DB", "X2TEXT"];

  const labelMap = {
    LLM: "Default LLM",
    EMBEDDING: "Default Embeddings",
    VECTOR_DB: "Default Vector DB",
    X2TEXT: "Default X2Text",
  };

  const updateDropdownData = (data) => {
    const updatedData = data.map((entry) => {
      if (entry.is_default) {
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

  const fetchData = async () => {
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`
      );
      updateDropdownData(response?.data);
      const defaultValues = {};
      response?.data.forEach((item) => {
        if (item.is_default) {
          defaultValues[item.adapter_type] = item.id;
        }
      });
      setSelectedValues(defaultValues);
    } catch (error) {
      console.error("Error fetching data:", error);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleDropdownChange = (adapterType, selectedValue) => {
    setSelectedValues((prevValues) => ({
      ...prevValues,
      [adapterType]: selectedValue,
    }));
    setIsSubmitEnabled(true);
  };

  // Handler for form submission
  const handleSubmit = async () => {
    try {
      const body = {
        llm_default: selectedValues[desiredOrder[0]],
        embedding_default: selectedValues[desiredOrder[1]],
        vector_db_default: selectedValues[desiredOrder[2]],
        x2text_default: selectedValues[desiredOrder[3]],
      };

      await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/adapter/default_triad/`,
        body,
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
        }
      );

      setAlertDetails({
        type: "success",
        content: "Default triad setting saved successfully",
      });
      fetchData();
      setIsSubmitEnabled(false);
    } catch (error) {
      setAlertDetails(handleException(error, "Failed to generate the key"));
    }
  };

  return (
    <>
      <div className="plt-set-head">
        <Button size="small" type="text" onClick={() => navigate(-1)}>
          <ArrowLeftOutlined />
        </Button>
        <Typography.Text className="plt-set-head-typo">
          Default Triad
        </Typography.Text>
      </div>
      <div className="plt-set-layout">
        <IslandLayout>
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
                    .filter((data) => data.adapter_type === type)
                    .map((data) => (
                      <Option key={data.id} value={data.id}>
                        {data.adapter_name}
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
        </IslandLayout>
      </div>
    </>
  );
}

export { DefaultTriad };
