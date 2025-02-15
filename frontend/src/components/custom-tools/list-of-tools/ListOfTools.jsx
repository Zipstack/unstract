import { PlusOutlined } from "@ant-design/icons";
import { useCallback, useMemo } from "react";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useListManager } from "../../../hooks/useListManager";
import ListOfToolsModal from "./ListOfToolsModal";
import { ListView } from "../../view-projects/ListView";

function ListOfTools() {
  const { setPostHogCustomEvent } = usePostHogEvents();

  const getBaseUrl = (sessionDetails) =>
    `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/`;

  const getListApiCall = useCallback(({ axiosPrivate, sessionDetails }) => {
    const baseUrl = getBaseUrl(sessionDetails);

    const requestOptions = {
      method: "GET",
      url: baseUrl,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };
    return axiosPrivate(requestOptions);
  }, []);

  const addItemApiCall = useCallback(
    ({ axiosPrivate, sessionDetails, itemData }) => {
      const baseUrl = getBaseUrl(sessionDetails);

      const requestOptions = {
        method: "POST",
        url: baseUrl,
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
      const baseUrl = getBaseUrl(sessionDetails);

      const requestOptions = {
        method: "PATCH",
        url: `${baseUrl}${itemId}/`,
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
      const baseUrl = getBaseUrl(sessionDetails);

      const requestOptions = {
        method: "DELETE",
        url: `${baseUrl}${itemId}`,
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
    searchProperty: "tool_name",
    itemIdProp: "tool_id",
    itemNameProp: "tool_name",
    itemDescriptionProp: "description",
    itemType: "Prompt Project",
  });

  const itemProps = useMemo(
    () => ({
      titleProp: "tool_name",
      descriptionProp: "description",
      iconProp: "icon",
      idProp: "tool_id",
      type: "Prompt Project",
    }),
    []
  );

  return (
    <ListView
      title="Prompt Studio"
      useListManagerHook={useListManagerHook}
      CustomModalComponent={ListOfToolsModal}
      customButtonText="New Project"
      customButtonIcon={<PlusOutlined />}
      itemProps={itemProps}
      setPostHogCustomEvent={setPostHogCustomEvent}
      newButtonEventName="intent_new_ps_project"
    />
  );
}

export { ListOfTools };
