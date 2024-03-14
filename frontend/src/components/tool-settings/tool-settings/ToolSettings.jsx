import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { IslandLayout } from "../../../layouts/island-layout/IslandLayout";
import { AddSourceModal } from "../../input-output/add-source-modal/AddSourceModal";
import "../../input-output/data-source-card/DataSourceCard.css";
import "./ToolSettings.css";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import { ViewTools } from "../../custom-tools/view-tools/ViewTools";
import { SharePermission } from "../../widgets/share-permission/SharePermission";

const titles = {
  llm: "LLMs",
  vector_db: "Vector DBs",
  embedding: "Embeddings",
  x2text: "Text Extractor",
  ocr: "OCR",
};

const btnText = {
  llm: "New LLM Profile",
  vector_db: "New Vector DB Profile",
  embedding: "New Embedding Profile",
  x2text: "New Text Extractor",
  ocr: "New OCR",
};

function ToolSettings({ type }) {
  const [tableRows, setTableRows] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isShareLoading, setIsShareLoading] = useState(false);
  const [adapterDetails, setAdapterDetails] = useState(null);
  const [userList, setUserList] = useState([]);
  const [openAddSourcesModal, setOpenAddSourcesModal] = useState(false);
  const [openSharePermissionModal, setopenSharePermissionModal] =
    useState(false);
  const [isPermissonEdit, setIsPermissionEdit] = useState(false);
  const [editItemId, setEditItemId] = useState(null);
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    setTableRows([]);
    if (!type) {
      return;
    }
    getAdapters();
  }, [type]);

  const getAdapters = () => {
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
  };

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

  const handleDelete = (_event, adapter) => {
    const requestOptions = {
      method: "DELETE",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const filteredList = tableRows.filter((row) => row?.id !== adapter.id);
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

  const handleShare = (_event, adapter, isEdit) => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/users/${adapter.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    setIsShareLoading(true);
    getAllUsers();
    axiosPrivate(requestOptions)
      .then((res) => {
        setopenSharePermissionModal(true);
        setAdapterDetails(res.data);
        setIsPermissionEdit(isEdit);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsShareLoading(false);
      });
  };

  const getAllUsers = () => {
    setIsShareLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/users/`,
    };

    axiosPrivate(requestOptions)
      .then((response) => {
        const users = response?.data?.members || [];
        setUserList(
          users.map((user) => ({
            id: user.id,
            email: user.email,
          }))
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load"));
      })
      .finally(() => {
        setIsShareLoading(false);
      });
  };

  const onShare = (userIds, adapter) => {
    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: { shared_users: userIds },
    };
    axiosPrivate(requestOptions)
      .then((response) => {
        setopenSharePermissionModal(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load"));
      });
  };

  return (
    <div className="plt-tool-settings-layout">
      <ToolNavBar
        title={titles[type]}
        CustomButtons={() => {
          return (
            <CustomButton
              type="primary"
              onClick={() => setOpenAddSourcesModal(true)}
              icon={<PlusOutlined />}
            >
              {btnText[type]}
            </CustomButton>
          );
        }}
      />
      <IslandLayout>
        <div className="plt-tool-settings-layout-2">
          <div className="plt-tool-settings-body">
            <ViewTools
              listOfTools={tableRows}
              isLoading={isLoading}
              handleDelete={handleDelete}
              setOpenAddTool={setOpenAddSourcesModal}
              handleEdit={(_event, item) => setEditItemId(item?.id)}
              idProp="id"
              titleProp="adapter_name"
              iconProp="icon"
              isEmpty={!tableRows?.length}
              centered
              isClickable={false}
              handleShare={handleShare}
              showOwner={true}
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
      <SharePermission
        open={openSharePermissionModal}
        setOpen={setopenSharePermissionModal}
        adapter={adapterDetails}
        permissionEdit={isPermissonEdit}
        loading={isShareLoading}
        allUsers={userList}
        onApply={onShare}
      />
    </div>
  );
}

ToolSettings.propTypes = {
  type: PropTypes.string.isRequired,
};

export { ToolSettings };
