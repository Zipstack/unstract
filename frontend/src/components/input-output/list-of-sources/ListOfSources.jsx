import { SearchOutlined } from "@ant-design/icons";
import { Input, List } from "antd";
import debounce from "lodash/debounce";
import PropTypes from "prop-types";
import { useCallback, useEffect, useState } from "react";

import { sourceTypes } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { DataSourceCard } from "../data-source-card/DataSourceCard";
import "./ListOfSources.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function ListOfSources({ setSelectedSourceId, type }) {
  const [sourcesList, setSourcesList] = useState([]);
  const [filteredSourcesList, setFilteredSourcesList] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  const disabledIdsByType = {
    EMBEDDING: ["huggingface|90ec9ec2-1768-4d69-8fb1-c88b95de5e5a"],
    LLM: ["replicate|2715ce84-05af-4ab4-b8e9-67ac3211b81e"],
    VECTOR_DB: ["milvus|3f42f6f9-4b8e-4546-95f3-22ecc9aca442"],
  };

  useEffect(() => {
    if (searchText?.length === 0) {
      setFilteredSourcesList(sourcesList);
    }
    const filteredList = [...sourcesList].filter((source) => {
      const name = source?.name?.toUpperCase();
      const searchUpperCase = searchText.toUpperCase();
      return name.includes(searchUpperCase);
    });
    setFilteredSourcesList(filteredList);
  }, [sourcesList, searchText]);

  useEffect(() => {
    if (!type) {
      setSourcesList([]);
      return;
    }
    getListOfSources();
  }, [type, open]);

  const getListOfSources = () => {
    let url = `/api/v1/unstract/${sessionDetails?.orgId}`;
    if (sourceTypes.connectors.includes(type)) {
      url += `/supported_connectors/?type=${type.toUpperCase()}`;
    } else {
      url += `/supported_adapters/?adapter_type=${type.toUpperCase()}`;
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

  const onSearchDebounce = useCallback(
    debounce(({ target: { value } }) => {
      setSearchText(value);
    }, 600),
    []
  );

  if (isLoading) {
    return <SpinnerLoader />;
  }

  return (
    <div className="list-of-srcs">
      <div className="searchbox">
        <Input
          placeholder="Search"
          prefix={<SearchOutlined className="search-outlined" />}
          onChange={onSearchDebounce}
          value={searchText}
        />
      </div>
      <div className="list">
        <List
          grid={{ gutter: 16, column: 4 }}
          dataSource={filteredSourcesList}
          renderItem={(srcDetails) => (
            <List.Item>
              <DataSourceCard
                srcDetails={srcDetails}
                setSelectedSourceId={setSelectedSourceId}
              />
            </List.Item>
          )}
        />
      </div>
    </div>
  );
}

ListOfSources.propTypes = {
  setSelectedSourceId: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
};

export { ListOfSources };
