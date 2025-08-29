import { Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { AddSource } from "../add-source/AddSource";
import { ListOfSources } from "../list-of-sources/ListOfSources";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import useRequestUrl from "../../../hooks/useRequestUrl";

function AddSourceModal({
  open,
  setOpen,
  type,
  isConnector,
  connectorMode,
  addNewItem,
  editItemId,
  setEditItemId,
}) {
  const [selectedSourceId, setSelectedSourceId] = useState(null);
  const [metadata, setMetadata] = useState({});
  const [titles, setTitles] = useState({});
  const [selectedSourceName, setSelectedSourceName] = useState("");
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { getUrl } = useRequestUrl();
  const [isLoading, setIsLoading] = useState(false);
  const [sourcesList, setSourcesList] = useState([]);

  const disabledIdsByType = {
    EMBEDDING: ["huggingface|90ec9ec2-1768-4d69-8fb1-c88b95de5e5a"],
    LLM: ["replicate|2715ce84-05af-4ab4-b8e9-67ac3211b81e"],
    VECTOR_DB: [],
  };

  useEffect(() => {
    const addOrEdit = editItemId?.length ? "Edit" : "Add";
    setTitles({
      llm: addOrEdit + " LLM",
      vector_db: addOrEdit + " Vector DB",
      embedding: addOrEdit + " Embedding",
      x2text: addOrEdit + " Text Extractor",
      connectors: addOrEdit + " Connector",
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

    getListOfSources();
  }, [open]);

  useEffect(() => {
    const selectedSource = sourcesList.find(
      (item) => item?.id === selectedSourceId
    );
    setSelectedSourceName(selectedSource?.name);
  }, [selectedSourceId]);

  const getSourceDetails = () => {
    let url;
    if (isConnector) {
      url = getUrl(`connector/${editItemId}/`);
    } else {
      url = getUrl(`adapter/${editItemId}/`);
    }

    const requestOptions = {
      method: "GET",
      url,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        setOpen(true);
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
        setOpen(false);
        setEditItemId(null);
      });
  };

  const getListOfSources = () => {
    let url;
    if (isConnector) {
      url = connectorMode
        ? getUrl(`supported_connectors/?connector_mode=${connectorMode}`)
        : getUrl(`supported_connectors/`);
    } else {
      if (!type) return;
      url = getUrl(`supported_adapters/?adapter_type=${type.toUpperCase()}`);
    }
    // API to get the list of adapters.
    const requestOptions = {
      method: "GET",
      url,
    };

    setIsLoading(true);
    setSourcesList([]);
    axiosPrivate(requestOptions)
      .then((res) => {
        const sources = res?.data || [];
        const updatedSources = sources?.map((source) => ({
          ...source,
          isDisabled: disabledIdsByType[source?.adapter_type]?.includes(
            source?.id
          ),
        }));
        setSourcesList(updatedSources || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoading(false);
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
      title={isConnector ? titles["connectors"] : titles[type]}
      width={selectedSourceId?.length ? 500 : 1100}
      centered
      footer={null}
      closable={true}
    >
      {selectedSourceId ? (
        <AddSource
          selectedSourceId={selectedSourceId}
          selectedSourceName={selectedSourceName}
          setOpen={setOpen}
          type={type}
          isConnector={isConnector}
          addNewItem={addNewItem}
          editItemId={editItemId}
          metadata={metadata}
        />
      ) : isLoading ? (
        <SpinnerLoader />
      ) : (
        <ListOfSources
          setSelectedSourceId={setSelectedSourceId}
          open={open}
          sourcesList={sourcesList}
          type={type}
        />
      )}
    </Modal>
  );
}

AddSourceModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  type: PropTypes.any,
  isConnector: PropTypes.bool,
  connectorMode: PropTypes.string,
  addNewItem: PropTypes.func.isRequired,
  editItemId: PropTypes.string,
  setEditItemId: PropTypes.func.isRequired,
};

AddSourceModal.defaultProps = {
  isConnector: false,
};

export { AddSourceModal };
