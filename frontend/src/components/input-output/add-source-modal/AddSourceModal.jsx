import { Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { sourceTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { AddSource } from "../add-source/AddSource";
import { ListOfSources } from "../list-of-sources/ListOfSources";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function AddSourceModal({
  open,
  setOpen,
  type,
  addNewItem,
  editItemId,
  setEditItemId,
}) {
  const [selectedSourceId, setSelectedSourceId] = useState(null);
  const [metadata, setMetadata] = useState({});
  const [titles, setTitles] = useState({});
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    const addOrEdit = editItemId?.length ? "Edit" : "Add";
    setTitles({
      input: addOrEdit + " Data Source",
      output: addOrEdit + " Data Destination",
      llm: addOrEdit + " LLM",
      vector_db: addOrEdit + " Vector DB",
      embedding: addOrEdit + " Embedding",
    });

    if (editItemId?.length) {
      getSourceDetails();
    }
  }, [editItemId]);

  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        // A delay added in order to avoid glitch in the UI when the modal is closed.
        setSelectedSourceId(null);
        setEditItemId(null);
      }, 500);
    }
  }, [open]);

  const getSourceDetails = () => {
    setOpen(true);

    const isConnector = sourceTypes.connectors.includes(type);
    let url = `/api/v1/unstract/${sessionDetails?.orgId}`;
    if (isConnector) {
      url += `/connector/${editItemId}/`;
    } else {
      url += `/adapter/${editItemId}/`;
    }

    const requestOptions = {
      method: "GET",
      url,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        if (isConnector) {
          setSelectedSourceId(data?.connector_id);
          const connectorMetadata = data?.connector_metadata;
          connectorMetadata["connectorName"] = data?.connector_name;
          setMetadata(connectorMetadata);
        } else {
          setSelectedSourceId(data?.adapter_id);
          const adapterMetadata = data?.adapter_metadata;
          adapterMetadata["adapter_name"] = data?.adapter_name;
          setMetadata(adapterMetadata);
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  return (
    <Modal
      open={open}
      onCancel={() => {
        setOpen(false);
        setMetadata(null);
      }}
      maskClosable={false}
      title={titles[type]}
      width={selectedSourceId?.length ? 500 : 1100}
      centered
      footer={null}
      closable={true}
    >
      {selectedSourceId ? (
        <AddSource
          selectedSourceId={selectedSourceId}
          setOpen={setOpen}
          type={type}
          addNewItem={addNewItem}
          editItemId={editItemId}
          metadata={metadata}
        />
      ) : (
        <ListOfSources setSelectedSourceId={setSelectedSourceId} type={type} />
      )}
    </Modal>
  );
}

AddSourceModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  addNewItem: PropTypes.func.isRequired,
  editItemId: PropTypes.string,
  setEditItemId: PropTypes.func.isRequired,
};

export { AddSourceModal };
