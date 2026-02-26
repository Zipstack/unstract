import { useCallback, useState } from "react";

import { useExceptionHandler } from "./useExceptionHandler";

function useCoOwnerManagement({ service, setAlertDetails, onListRefresh }) {
  const handleException = useExceptionHandler();

  const [coOwnerOpen, setCoOwnerOpen] = useState(false);
  const [coOwnerData, setCoOwnerData] = useState({
    coOwners: [],
    createdBy: null,
  });
  const [coOwnerLoading, setCoOwnerLoading] = useState(false);
  const [coOwnerAllUsers, setCoOwnerAllUsers] = useState([]);
  const [coOwnerResourceId, setCoOwnerResourceId] = useState(null);

  const refreshCoOwnerData = useCallback(
    async (resourceId) => {
      try {
        const res = await service.getSharedUsers(resourceId);
        setCoOwnerData({
          coOwners: res.data?.co_owners || [],
          createdBy: res.data?.created_by || null,
        });
      } catch (err) {
        if (err?.response?.status === 404) {
          setCoOwnerOpen(false);
          onListRefresh?.();
          setAlertDetails({
            type: "error",
            content:
              "This resource is no longer accessible. It may have been removed or your access has been revoked.",
          });
          return;
        }
        setAlertDetails(
          handleException(err, "Unable to refresh co-owner data"),
        );
      }
    },
    [service, onListRefresh, setAlertDetails, handleException],
  );

  const handleCoOwner = useCallback(
    async (resourceId) => {
      setCoOwnerResourceId(resourceId);
      setCoOwnerLoading(true);
      setCoOwnerOpen(true);

      try {
        const [usersResponse, sharedUsersResponse] = await Promise.all([
          service.getAllUsers(),
          service.getSharedUsers(resourceId),
        ]);

        const userList =
          usersResponse?.data?.members?.map((member) => ({
            id: member.id,
            email: member.email,
          })) || [];

        setCoOwnerAllUsers(userList);
        setCoOwnerData({
          coOwners: sharedUsersResponse.data?.co_owners || [],
          createdBy: sharedUsersResponse.data?.created_by || null,
        });
      } catch (err) {
        setAlertDetails(
          handleException(err, "Unable to fetch co-owner information"),
        );
        setCoOwnerOpen(false);
      } finally {
        setCoOwnerLoading(false);
      }
    },
    [service, setAlertDetails, handleException],
  );

  const onAddCoOwner = useCallback(
    async (resourceId, userIdOrIds) => {
      const isBatch = Array.isArray(userIdOrIds);
      const userIds = isBatch ? userIdOrIds : [userIdOrIds];
      try {
        for (const userId of userIds) {
          await service.addCoOwner(resourceId, userId);
        }
        setAlertDetails({
          type: "success",
          content: isBatch
            ? "Co-owners added successfully"
            : "Co-owner added successfully",
        });
        await refreshCoOwnerData(resourceId);
        onListRefresh?.();
      } catch (err) {
        setAlertDetails(handleException(err, "Unable to add co-owner"));
        if (isBatch) {
          await refreshCoOwnerData(resourceId);
          onListRefresh?.();
        }
      }
    },
    [
      service,
      refreshCoOwnerData,
      onListRefresh,
      setAlertDetails,
      handleException,
    ],
  );

  const onRemoveCoOwner = useCallback(
    async (resourceId, userId) => {
      try {
        await service.removeCoOwner(resourceId, userId);
        setAlertDetails({
          type: "success",
          content: "Co-owner removed successfully",
        });
        await refreshCoOwnerData(resourceId);
        onListRefresh?.();
      } catch (err) {
        setAlertDetails(handleException(err, "Unable to remove co-owner"));
      }
    },
    [
      service,
      refreshCoOwnerData,
      onListRefresh,
      setAlertDetails,
      handleException,
    ],
  );

  return {
    coOwnerOpen,
    setCoOwnerOpen,
    coOwnerData,
    coOwnerLoading,
    coOwnerAllUsers,
    coOwnerResourceId,
    handleCoOwner,
    onAddCoOwner,
    onRemoveCoOwner,
  };
}

export { useCoOwnerManagement };
