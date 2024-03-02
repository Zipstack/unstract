import {
  AppstoreOutlined,
  BarsOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Input, Segmented, Typography } from "antd";
import debounce from "lodash/debounce";
import isEmpty from "lodash/isEmpty";
import { useCallback, useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { AddCustomToolFormModal } from "../add-custom-tool-form-modal/AddCustomToolFormModal";
import { ViewTools } from "../view-tools/ViewTools";

import { handleException } from "../../../helpers/GetStaticData";
import "./ListOfTools.css";

const { Search } = Input;

function ListOfTools() {
  const VIEW_OPTIONS = [
    {
      value: "grid",
      icon: <AppstoreOutlined />,
    },
    {
      value: "list",
      icon: <BarsOutlined />,
    },
  ];
  const [viewType, setViewType] = useState(VIEW_OPTIONS[0].value);
  const [isListLoading, setIsListLoading] = useState(false);
  const [openAddTool, setOpenAddTool] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  const [listOfTools, setListOfTools] = useState([]);
  const [filteredListOfTools, setFilteredListOfTools] = useState([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    getListOfTools();
  }, []);

  const getListOfTools = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/ `,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    setIsListLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setListOfTools(data);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(err, "Failed to get the list of tools")
        );
      })
      .finally(() => {
        setIsListLoading(false);
      });
  };

  const handleAddNewTool = (body) => {
    let method = "POST";
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`;
    const isEdit = editItem && Object.keys(editItem)?.length > 0;
    if (isEdit) {
      method = "PATCH";
      url += `${editItem?.tool_id}/`;
    }
    return new Promise((resolve, reject) => {
      const requestOptions = {
        method,
        url,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: body,
      };

      axiosPrivate(requestOptions)
        .then((res) => {
          const tool = res?.data;
          updateList(isEdit, tool);
          setOpenAddTool(false);
          resolve(true);
        })
        .catch((err) => {
          reject(err);
        });
    });
  };

  const updateList = (isEdit, data) => {
    let tools = [...listOfTools];

    if (isEdit) {
      tools = tools.map((item) =>
        item?.tool_id === data?.tool_id ? data : item
      );
      setEditItem(null);
    } else {
      tools.push(data);
    }
    setListOfTools(tools);
  };

  const handleEdit = (event, id) => {
    event.domEvent.stopPropagation();
    const editToolData = [...listOfTools].find((item) => item?.tool_id === id);
    if (!editToolData) {
      return;
    }
    setEditItem(editToolData);
    setOpenAddTool(true);
  };

  const handleDelete = (event, id) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const tools = [...listOfTools].filter((tool) => tool?.tool_id !== id);
        setListOfTools(tools);
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          // TODO: Handle with generic function to parse drf-validation error messages
          // Here we assume its either a server error or display a generic message
          content: err?.response?.data?.errors[0].detail || "Failed to delete",
        });
      });
  };

  const handleViewChange = (type) => {
    setViewType(type);
  };

  useEffect(() => {
    if (search?.length === 0) {
      setFilteredListOfTools(listOfTools);
    }
    const filteredList = [...listOfTools].filter((tool) => {
      const name = tool.tool_name?.toUpperCase();
      const searchUpperCase = search.toUpperCase();
      return name.includes(searchUpperCase);
    });
    setFilteredListOfTools(filteredList);
  }, [search, listOfTools]);

  const onSearchDebounce = useCallback(
    debounce(({ target: { value } }) => {
      setSearch(value);
    }, 600),
    []
  );

  return (
    <>
      <div className="list-of-tools-layout">
        <div className="list-of-tools-island">
          <div direction="vertical" className="list-of-tools-wrap">
            <div className="list-of-tools-header">
              <Typography.Text className="list-of-tools-title">
                Prompt Studio
              </Typography.Text>
              <div className="list-of-tools-header2">
                <Segmented
                  options={VIEW_OPTIONS}
                  value={viewType}
                  onChange={handleViewChange}
                />
                <Search
                  disabled={isEmpty(listOfTools)}
                  placeholder="Search by tool name"
                  onChange={onSearchDebounce}
                  allowClear
                />
                <CustomButton
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setOpenAddTool(true)}
                >
                  New Tool
                </CustomButton>
              </div>
            </div>
            <div className="list-of-tools-divider" />
            <div className="list-of-tools-body">
              <ViewTools
                isLoading={isListLoading}
                viewType={viewType}
                isEmpty={!listOfTools?.length}
                listOfTools={filteredListOfTools}
                setOpenAddTool={setOpenAddTool}
                handleEdit={handleEdit}
                handleDelete={handleDelete}
              />
            </div>
          </div>
        </div>
      </div>
      <AddCustomToolFormModal
        open={openAddTool}
        setOpen={setOpenAddTool}
        editItem={editItem}
        setEditItem={setEditItem}
        handleAddNewTool={handleAddNewTool}
      />
    </>
  );
}

export { ListOfTools };
