import { PlusOutlined } from "@ant-design/icons";
import { Typography } from "antd";
import PropTypes from "prop-types";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import "../../input-output/data-source-card/DataSourceCard.css";
import "./ToolSettings.css";

import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { ListOfItems } from "../list-of-items/ListOfItems";

const titles = {
  llm: "LLMs",
  vector_db: "Vector DBs",
  embedding: "Embeddings",
  x2text: "Text Extractor",
};

const btnText = {
  llm: "New LLM Profile",
  vector_db: "New Vector DB Profile",
  embedding: "New Embedding Profile",
  x2text: "New Text Extractor",
};

function ToolSettings({ type }) {
  const [tableRows, setTableRows] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [openAddSourcesModal, setOpenAddSourcesModal] = useState(false);
  const [editItemId, setEditItemId] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    setTableRows([]);
    if (!type) {
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${
        sessionDetails?.orgId
      }/adapter?adapter_type=${type.toUpperCase()}`,
    };
    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        setTableRows(res?.data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [type]);

  const addNewItem = (row, isEdit) => {
    if (isEdit) {
      const rowsModified = [...tableRows].map((tableRow) => {
        if (tableRow?.id !== row?.id) {
          return tableRow;
        }
        tableRow["adapter_name"] = row?.adapter_name;
        return tableRow;
      });
      setTableRows(rowsModified);
    } else {
      const rowsModified = [...tableRows];
      rowsModified.push(row);
      setTableRows(rowsModified);
    }
  };

  const handleDelete = (id) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const filteredList = tableRows.filter((row) => row?.id !== id);
        setTableRows(filteredList);
        setAlertDetails({
          type: "success",
          content: "Successfully deleted",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  return (
    <div className="plt-tool-settings-layout">
      <IslandLayout>
        <div className="plt-tool-settings-layout-2">
          <div className="plt-tool-settings-header">
            <div className="plt-tool-settings-title">
              <Typography.Text className="typo-text" strong>
                {titles[type]}
              </Typography.Text>
            </div>
            <div className="plt-tool-settings-add-btn">
              <CustomButton
                type="primary"
                onClick={() => setOpenAddSourcesModal(true)}
                icon={<PlusOutlined />}
              >
                {btnText[type]}
              </CustomButton>
            </div>
          </div>
          <div className="plt-tool-settings-body">
            <ListOfItems
              isLoading={isLoading}
              tableRows={tableRows}
              setEditItemId={setEditItemId}
              handleDelete={handleDelete}
              handleClick={() => setOpenAddSourcesModal(true)}
            />
          </div>
        </div>
      </IslandLayout>
      <AddSourceModal
        open={openAddSourcesModal}
        setOpen={setOpenAddSourcesModal}
        type={type}
        addNewItem={addNewItem}
        editItemId={editItemId}
        setEditItemId={setEditItemId}
      />
    </div>
  );
}

ToolSettings.propTypes = {
  type: PropTypes.string.isRequired,
};

export { ToolSettings };
