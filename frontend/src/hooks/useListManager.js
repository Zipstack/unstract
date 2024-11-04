import { useState, useEffect } from "react";
import { useExceptionHandler } from "./useExceptionHandler";
import { useAlertStore } from "../store/alert-store";
import { useSessionStore } from "../store/session-store";
import { useAxiosPrivate } from "./useAxiosPrivate";

export function useListManager({
  getListApiCall,
  addItemApiCall,
  editItemApiCall,
  deleteItemApiCall,
  searchProperty = "",
  itemIdProp = "id",
  itemType = "item",
  initialFilter,
  onAddSuccess,
  onEditSuccess,
  onDeleteSuccess,
  onError,
}) {
  const [list, setList] = useState([]);
  const [filteredList, setFilteredList] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const sessionDetails = useSessionStore((state) => state?.sessionDetails);
  const axiosPrivate = useAxiosPrivate();

  useEffect(() => {
    fetchList();
  }, [initialFilter]);

  const fetchList = () => {
    if (!getListApiCall) return;

    setLoading(true);
    getListApiCall({ axiosPrivate, sessionDetails, initialFilter })
      .then((res) => {
        const data = res?.data || [];
        setList(data);
        setFilteredList(data);
      })
      .catch((err) => {
        const errorMsg = handleException(
          err,
          `Failed to get the list of ${itemType}s`
        );
        setAlertDetails(errorMsg);
        onError?.(err);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const updateList = (itemData, isEdit = false, itemId) => {
    let updatedList = [];

    if (isEdit) {
      updatedList = list.map((item) =>
        item?.[itemIdProp] === itemId ? itemData : item
      );
      onEditSuccess?.(itemData);
    } else {
      updatedList = [itemData, ...list];
      onAddSuccess?.(itemData);
    }

    setList(updatedList);
    setFilteredList(updatedList);
  };

  const handleSearch = (searchText = "") => {
    if (!searchText.trim()) {
      setFilteredList(list);
      return;
    }
    const filtered = list.filter((item) =>
      item?.[searchProperty]?.toLowerCase()?.includes(searchText.toLowerCase())
    );
    setFilteredList(filtered);
  };

  const handleAddItem = (itemData, isEdit = false, itemId) => {
    const apiCall = isEdit ? editItemApiCall : addItemApiCall;
    if (!apiCall) return Promise.reject(new Error("API call is not defined"));

    return apiCall({ axiosPrivate, sessionDetails, itemData, itemId })
      .then((res) => {
        const updatedItem = res?.data;
        let updatedList = [];

        if (isEdit) {
          updatedList = list.map((item) =>
            item?.[itemIdProp] === itemId ? updatedItem : item
          );
          onEditSuccess?.(updatedItem);
        } else {
          updatedList = [...list, updatedItem];
          onAddSuccess?.(updatedItem);
        }

        setList(updatedList);
        setFilteredList(updatedList);
        return updatedItem;
      })
      .catch((err) => {
        const errorMsg = handleException(
          err,
          `Failed to ${isEdit ? "edit" : "add"} ${itemType}`
        );
        setAlertDetails(errorMsg);
        onError?.(err);
        throw err;
      });
  };

  const handleDeleteItem = (itemId) => {
    if (!deleteItemApiCall)
      return Promise.reject(new Error("API call is not defined"));

    return deleteItemApiCall({ axiosPrivate, sessionDetails, itemId })
      .then(() => {
        const updatedList = list.filter(
          (item) => item?.[itemIdProp] !== itemId
        );
        setList(updatedList);
        setFilteredList(updatedList);
        onDeleteSuccess?.(itemId);
      })
      .catch((err) => {
        const errorMsg = handleException(err, `Failed to delete ${itemType}`);
        setAlertDetails(errorMsg);
        onError?.(err);
        throw err;
      });
  };

  return {
    list,
    filteredList,
    updateList,
    loading,
    fetchList,
    handleSearch,
    handleAddItem,
    handleDeleteItem,
  };
}
