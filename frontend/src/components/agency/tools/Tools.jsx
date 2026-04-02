import { SearchOutlined } from "@ant-design/icons";
import { Input } from "antd";
import debounce from "lodash/debounce";
import { useCallback, useEffect, useState } from "react";
import "./Tools.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ListOfTools } from "../list-of-tools/ListOfTools";

function Tools() {
  const [listOfTools, setListOfTools] = useState([]);
  const [filteredListOfTools, setFilteredListOfTools] = useState([]);
  const [isLoading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    setLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/tool/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        setListOfTools(res?.data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (search?.length === 0) {
      setFilteredListOfTools(listOfTools);
    }
    const filteredList = [...listOfTools].filter((tool) => {
      const name = tool?.name;
      if (!name) {
        return false;
      }
      const searchUpperCase = search.toUpperCase();
      return name?.toUpperCase().includes(searchUpperCase);
    });
    setFilteredListOfTools(filteredList);
  }, [search, listOfTools]);

  const onSearchDebounce = useCallback(
    debounce(({ target: { value } }) => {
      setSearch(value);
    }, 600),
    [],
  );

  return (
    <div className="wf-tools-layout">
      <div className="wf-tools-search">
        <Input
          className="tool-chest-input"
          placeholder="Search for tool"
          onChange={onSearchDebounce}
          prefix={<SearchOutlined className="icon" />}
        />
      </div>
      <div className="wf-tools-list">
        <ListOfTools listOfTools={filteredListOfTools} isLoading={isLoading} />
      </div>
    </div>
  );
}

export { Tools };
