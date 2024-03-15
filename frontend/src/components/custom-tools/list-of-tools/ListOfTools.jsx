import { PlusOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { AddCustomToolFormModal } from "../add-custom-tool-form-modal/AddCustomToolFormModal";
import { ViewTools } from "../view-tools/ViewTools";
import "./ListOfTools.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";

function ListOfTools() {
  const [isListLoading, setIsListLoading] = useState(false);
  const [openAddTool, setOpenAddTool] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  const [listOfTools, setListOfTools] = useState([]);
  const [filteredListOfTools, setFilteredListOfTools] = useState([]);
  const handleException = useExceptionHandler();
  const [isEdit, setIsEdit] = useState(false);

  useEffect(() => {
    getListOfTools();
  }, []);

  useEffect(() => {
    setFilteredListOfTools(listOfTools);
  }, [listOfTools]);

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
        setFilteredListOfTools(data);
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

  const handleEdit = (_event, tool) => {
    const editToolData = [...listOfTools].find(
      (item) => item?.tool_id === tool.tool_id
    );
    if (!editToolData) {
      return;
    }
    setIsEdit(true);
    setEditItem(editToolData);
    setOpenAddTool(true);
  };

  const handleDelete = (_event, tool) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${tool.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then(() => {
        const tools = [...listOfTools].filter(
          (filterToll) => filterToll?.tool_id !== tool.tool_id
        );
        setListOfTools(tools);
        setAlertDetails({
          type: "success",
          console: "Deleted successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to Delete"));
      });
  };

  const onSearch = (search, setSearch) => {
    if (search?.length === 0) {
      setSearch(listOfTools);
    }
    const filteredList = [...listOfTools].filter((tool) => {
      const name = tool.tool_name?.toUpperCase();
      const searchUpperCase = search.toUpperCase();
      return name.includes(searchUpperCase);
    });
    setSearch(filteredList);
  };

  const showAddTool = () => {
    setEditItem(null);
    setIsEdit(false);
    setOpenAddTool(true);
  };

  const CustomButtons = () => {
    return (
      <CustomButton
        type="primary"
        icon={<PlusOutlined />}
        onClick={showAddTool}
      >
        New Project
      </CustomButton>
    );
  };

  return (
    <>
      <ToolNavBar
        title={"Prompt Studio"}
        enableSearch
        onSearch={onSearch}
        searchList={listOfTools}
        setSearchList={setFilteredListOfTools}
        CustomButtons={CustomButtons}
      />
      <div className="list-of-tools-layout">
        <div className="list-of-tools-island">
          <div className="list-of-tools-body">
            <ViewTools
              isLoading={isListLoading}
              isEmpty={!listOfTools?.length}
              listOfTools={filteredListOfTools}
              setOpenAddTool={setOpenAddTool}
              handleEdit={handleEdit}
              handleDelete={handleDelete}
              titleProp="tool_name"
              descriptionProp="description"
              iconProp="icon"
              idProp="tool_id"
              type="Prompt Project"
            />
          </div>
        </div>
      </div>
      {openAddTool && (
        <AddCustomToolFormModal
          open={openAddTool}
          setOpen={setOpenAddTool}
          editItem={editItem}
          isEdit={isEdit}
          handleAddNewTool={handleAddNewTool}
        />
      )}
    </>
  );
}

export { ListOfTools };
