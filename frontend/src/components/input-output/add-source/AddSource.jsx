import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { handleException, sourceTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { ConfigureDs } from "../configure-ds/ConfigureDs";

function AddSource({
  selectedSourceId,
  setOpen,
  type,
  addNewItem,
  editItemId,
  metadata,
  handleUpdate,
}) {
  const [spec, setSpec] = useState({});
  const [formData, setFormData] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [oAuthProvider, setOAuthProvider] = useState("");
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    if (!selectedSourceId) {
      setSpec({});
      setOAuthProvider("");
      return;
    }

    let url = `/api/v1/unstract/${sessionDetails?.orgId}`;
    if (sourceTypes.connectors.includes(type)) {
      url += `/connector_schema/?id=${selectedSourceId}`;
    } else {
      url += `/adapter_schema/?id=${selectedSourceId}`;
    }

    const requestOptions = {
      method: "GET",
      url,
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setSpec(data?.json_schema || {});
        if (data?.oauth) {
          setOAuthProvider(data?.python_social_auth_backend);
        } else {
          setOAuthProvider("");
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [selectedSourceId]);

  useEffect(() => {
    if (editItemId?.length && metadata && Object.keys(metadata)?.length) {
      setFormData(metadata);
    }
  }, [metadata]);

  if (selectedSourceId.includes("pcs|")) {
    return (
      <Typography.Text>
        Edit is not supported for this connector
      </Typography.Text>
    );
  }

  if (!spec || !Object.keys(spec)?.length) {
    return <EmptyState text="Failed to load the settings form" />;
  }

  return (
    <ConfigureDs
      spec={spec}
      formData={formData}
      setFormData={setFormData}
      setOpen={setOpen}
      oAuthProvider={oAuthProvider}
      selectedSourceId={selectedSourceId}
      isLoading={isLoading}
      addNewItem={addNewItem}
      type={type}
      editItemId={editItemId}
      sourceType={
        sourceTypes.connectors.includes(type)
          ? Object.keys(sourceTypes)[0]
          : Object.keys(sourceTypes)[1]
      }
      handleUpdate={handleUpdate}
    />
  );
}

AddSource.propTypes = {
  selectedSourceId: PropTypes.string.isRequired,
  setOpen: PropTypes.func,
  type: PropTypes.string.isRequired,
  addNewItem: PropTypes.func,
  editItemId: PropTypes.string,
  metadata: PropTypes.object,
  handleUpdate: PropTypes.func,
};

export { AddSource };
