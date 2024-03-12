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
import "./DefaultTriad.css";

const { Option } = Select;

function DefaultTriad() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const [adaptorsList, setAdaptorsList] = useState([]);
  const [currentLLMDefault, setCurrentLLMDefault] = useState();
  const [currentVECTORDefault, setCurrentVECTORDefault] = useState();
  const [currentEMBDefault, setCurrentEMBDefault] = useState();

  const [selectedLLMDefault, setSelectedLLMDefault] = useState();
  const [selectedVECTORDefault, setSelectedVECTORDefault] = useState();
  const [selectedEMBDefault, setSelectedEMBDefault] = useState();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axiosPrivate.get(
          `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`
        );
        setAdaptorsList(res.data);

        const defaultAdaptorRes = await axiosPrivate.get(
          `/api/v1/unstract/${sessionDetails?.orgId}/adapter/default_triad/`
        );

        setCurrentLLMDefault(defaultAdaptorRes.data?.default_llm_adapter);
        setCurrentEMBDefault(defaultAdaptorRes.data?.default_llm_adapter);
        setCurrentVECTORDefault(defaultAdaptorRes.data?.default_llm_adapter);
      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };

    fetchData();
  }, []);

  useEffect(() => {
    setSelectedLLMDefault(currentLLMDefault);
    setSelectedEMBDefault(currentEMBDefault);
    setSelectedVECTORDefault(currentVECTORDefault);
  }, [adaptorsList.length > 0]);

  const onSubmit = async () => {
    if (
      currentLLMDefault === selectedLLMDefault &&
      currentEMBDefault === selectedEMBDefault &&
      currentVECTORDefault === selectedVECTORDefault
    ) {
      setAlertDetails({
        type: "warning",
        content: "Nothing new to save/update",
      });
      return;
    }

    try {
      const body = {
        llm_default: selectedLLMDefault,
        vector_db_default: selectedVECTORDefault,
        embedding_default: selectedEMBDefault,
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

      setCurrentEMBDefault(selectedEMBDefault);
      setCurrentLLMDefault(selectedLLMDefault);
      setCurrentVECTORDefault(selectedVECTORDefault);
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
            <SpaceWrapper>
              <Typography className="triad-select">Default LLM</Typography>
              <Select
                placeholder="Select LLM default"
                onChange={setSelectedLLMDefault}
                value={selectedLLMDefault}
                style={{ width: "100%" }}
              >
                {adaptorsList
                  .filter((item) => item.adapter_type === "LLM")
                  .map((item) => (
                    <Option key={item.id} value={item.id}>
                      {item.adapter_name}
                      {currentLLMDefault === item.id && " (current default)"}
                    </Option>
                  ))}
              </Select>
            </SpaceWrapper>
            <SpaceWrapper>
              <Typography className="triad-select">
                Default Embeddings
              </Typography>
              <Select
                placeholder="Select Embeddings default"
                onChange={setSelectedEMBDefault}
                value={selectedEMBDefault}
                style={{ width: "100%" }}
              >
                {adaptorsList
                  .filter((item) => item.adapter_type === "EMBEDDING")
                  .map((item) => (
                    <Option key={item.id} value={item.id}>
                      {item.adapter_name}
                      {currentEMBDefault === item.id && " (current default)"}
                    </Option>
                  ))}
              </Select>
            </SpaceWrapper>
            <SpaceWrapper>
              <Typography className="triad-select">
                Default Vector DB
              </Typography>
              <Select
                placeholder="Select VECTOR DB default"
                onChange={setSelectedVECTORDefault}
                value={selectedVECTORDefault}
                style={{ width: "100%" }}
              >
                {adaptorsList
                  .filter((item) => item.adapter_type === "VECTOR_DB")
                  .map((item) => (
                    <Option key={item.id} value={item.id}>
                      {item.adapter_name}
                      {currentVECTORDefault === item.id && " (current default)"}
                    </Option>
                  ))}
              </Select>
            </SpaceWrapper>
            <CustomButton
              type="primary"
              className="triad-select"
              onClick={onSubmit}
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
