import { Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import axios from "axios";

import "./EditDsModal.css";
import { ConfigureDs } from "../configure-ds/ConfigureDs.jsx";
import { useSessionStore } from "../../../store/session-store";
import { CONNECTOR_TYPE_MAP } from "../../../helpers/GetStaticData";
import { useAlertStore } from "../../../store/alert-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";

function EditDsModal({
  isOpen,
  setOpen,
  currentConnectorId,
  connectorType,
  setReloadList,
}) {
  const [dsSelected, setDsSelected] = useState("");
  const [spec, setSpec] = useState({});
  const [isSpecLoading, setIsSpecLoading] = useState(false);
  const [oAuthProvider, setOAuthProvider] = useState("");
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const [connectorData, setConnectorData] = useState({});

  const orgId = sessionDetails?.orgId;

  useEffect(() => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${orgId}/connector/${currentConnectorId}/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        setDsSelected(res?.data?.connector_id);
        setConnectorData(res?.data);
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          content: "Failed to fetch the connector data.",
        });
      });
  }, [currentConnectorId]);

  useEffect(() => {
    if (dsSelected.length === 0) return;
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${orgId}/connector_schema/?id=${dsSelected}`,
    };

    setIsSpecLoading(true);
    axios(requestOptions)
      .then((res) => {
        const data = res?.data;
        setSpec(data?.json_schema);
        if (data?.oauth) {
          setOAuthProvider(data?.python_social_auth_backend);
        }
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          content: "Failed to fetch the data source details.",
        });
      })
      .finally(() => {
        setIsSpecLoading(false);
      });
  }, [dsSelected]);

  const handleCancel = () => {
    setReloadList(true);
    setOpen(false);
  };

  return (
    <Modal
      className="edit-ds-modal"
      title={`Edit Data ${CONNECTOR_TYPE_MAP[connectorType]}`}
      open={isOpen}
      centered
      maskClosable={false}
      footer={null}
      onCancel={handleCancel}
    >
      <div className="edit-ds-layout">
        {connectorData && (
          <ConfigureDs
            spec={spec}
            oAuthProvider={oAuthProvider}
            dsSelected={dsSelected}
            isLoading={isSpecLoading}
            handleCancel={handleCancel}
            connectorType={connectorType}
            connectorData={connectorData}
          />
        )}
      </div>
    </Modal>
  );
}

EditDsModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  currentConnectorId: PropTypes.string,
  connectorType: PropTypes.string,
  setReloadList: PropTypes.func.isRequired,
};

export { EditDsModal };
