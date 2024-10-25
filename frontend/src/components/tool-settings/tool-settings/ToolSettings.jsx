import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useState, useCallback, useMemo } from "react";

import { useSessionStore } from "../../../store/session-store";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useListManager } from "../../../hooks/useListManager";
import { ListView } from "../../view-projects/ListView";
import ToolSettingsModal from "./ToolSettingsModal";
import { SharePermission } from "../../widgets/share-permission/SharePermission";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";

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
  const { setPostHogCustomEvent, posthogEventText } = usePostHogEvents();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();

  const [adapterDetails, setAdapterDetails] = useState(null);
  const [userList, setUserList] = useState([]);
  const [isShareLoading, setIsShareLoading] = useState(false);
  const [openSharePermissionModal, setOpenSharePermissionModal] =
    useState(false);
  const [isPermissionEdit, setIsPermissionEdit] = useState(false);

  const getListApiCall = useCallback(
    ({ axiosPrivate, sessionDetails }) => {
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${
          sessionDetails?.orgId
        }/adapter?adapter_type=${type.toUpperCase()}`,
      };
      return axiosPrivate(requestOptions);
    },
    [type]
  );

  const addItemApiCall = useCallback(
    ({ axiosPrivate, sessionDetails, itemData }) => {
      const requestOptions = {
        method: "POST",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: itemData,
      };
      return axiosPrivate(requestOptions);
    },
    []
  );

  const editItemApiCall = useCallback(
    ({ axiosPrivate, sessionDetails, itemData, itemId }) => {
      const requestOptions = {
        method: "PATCH",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${itemId}/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
          "Content-Type": "application/json",
        },
        data: itemData,
      };
      return axiosPrivate(requestOptions);
    },
    []
  );

  const deleteItemApiCall = useCallback(
    ({ axiosPrivate, sessionDetails, itemId }) => {
      const requestOptions = {
        method: "DELETE",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${itemId}/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
        },
      };
      return axiosPrivate(requestOptions);
    },
    []
  );

  const useListManagerHook = useListManager({
    getListApiCall,
    addItemApiCall,
    editItemApiCall,
    deleteItemApiCall,
    searchProperty: "adapter_name",
    itemIdProp: "id",
    itemNameProp: "adapter_name",
    itemDescriptionProp: "description",
    itemType: "Adapter",
  });

  const getAllUsers = useCallback(() => {
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
  }, []);

  // Memoized handleShare function
  const handleShare = useCallback(
    (adapter, isEdit) => {
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
          setOpenSharePermissionModal(true);
          setAdapterDetails(res.data);
          setIsPermissionEdit(isEdit);
        })
        .catch((err) => {
          setAlertDetails(handleException(err));
        })
        .finally(() => {
          setIsShareLoading(false);
        });
    },
    [
      getAllUsers,
      setOpenSharePermissionModal,
      setAdapterDetails,
      setIsPermissionEdit,
    ]
  );

  const onShare = useCallback(
    (userIds, adapter) => {
      const requestOptions = {
        method: "PATCH",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/${adapter.id}/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
        },
        data: { shared_users: userIds },
      };
      axiosPrivate(requestOptions)
        .then(() => {
          setOpenSharePermissionModal(false);
        })
        .catch((err) => {
          setAlertDetails(handleException(err, "Failed to load"));
        });
    },
    [setOpenSharePermissionModal]
  );

  const itemProps = useMemo(
    () => ({
      titleProp: "adapter_name",
      descriptionProp: "description",
      iconProp: "icon",
      idProp: "id",
      type: "Adapter",
      handleShare,
      showOwner: true,
      isClickable: false,
      centered: true,
    }),
    [handleShare]
  );

  return (
    <>
      <ListView
        title={titles[type]}
        useListManagerHook={useListManagerHook}
        CustomModalComponent={ToolSettingsModal}
        customButtonText={btnText[type]}
        customButtonIcon={<PlusOutlined />}
        itemProps={itemProps}
        setPostHogCustomEvent={setPostHogCustomEvent}
        newButtonEventName={posthogEventText[type]}
        type={type}
      />
      <SharePermission
        open={openSharePermissionModal}
        setOpen={setOpenSharePermissionModal}
        adapter={adapterDetails}
        permissionEdit={isPermissionEdit}
        loading={isShareLoading}
        allUsers={userList}
        onApply={onShare}
      />
    </>
  );
}

ToolSettings.propTypes = {
  type: PropTypes.string.isRequired,
};

export { ToolSettings };
