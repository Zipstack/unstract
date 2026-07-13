import { useCallback, useRef, useState } from "react";

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
  const latestRequestRef = useRef(null);

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
      const requestId = {};
      latestRequestRef.current = requestId;
      setCoOwnerResourceId(resourceId);
      setCoOwnerLoading(true);
      setCoOwnerOpen(true);

      try {
        const [usersResponse, sharedUsersResponse] = await Promise.all([
          service.getAllUsers(),
          service.getSharedUsers(resourceId),
        ]);

        if (latestRequestRef.current !== requestId) return;

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
        if (latestRequestRef.current !== requestId) return;
        setAlertDetails(
          handleException(err, "Unable to fetch co-owner information"),
        );
        setCoOwnerOpen(false);
      } finally {
        if (latestRequestRef.current === requestId) {
          setCoOwnerLoading(false);
        }
      }
    },
    [service, setAlertDetails, handleException],
  );

  const onAddCoOwner = useCallback(
    async (resourceId, userIdOrIds) => {
      const isBatch = Array.isArray(userIdOrIds);
      const userIds = isBatch ? userIdOrIds : [userIdOrIds];
      // Attempt every id independently — a mid-batch failure must not drop the
      // remaining ids or contradict the refreshed modal state.
      const failedIds = [];
      let lastError = null;
      for (const userId of userIds) {
        try {
          await service.addCoOwner(resourceId, userId);
        } catch (err) {
          failedIds.push(userId);
          lastError = err;
        }
      }
      // Reconverge the modal on true server state regardless of partial outcome.
      await refreshCoOwnerData(resourceId);
      onListRefresh?.();

      const succeeded = userIds.length - failedIds.length;
      if (failedIds.length === 0) {
        setAlertDetails({
          type: "success",
          content: isBatch
            ? "Co-owners added successfully"
            : "Co-owner added successfully",
        });
      } else if (succeeded === 0) {
        setAlertDetails(handleException(lastError, "Unable to add co-owner"));
      } else {
        const failedEmails = coOwnerAllUsers
          .filter((user) => failedIds.includes(user.id))
          .map((user) => user.email);
        setAlertDetails({
          type: "warning",
          content: `Added ${succeeded} of ${userIds.length} co-owners. Failed for: ${
            failedEmails.join(", ") || failedIds.join(", ")
          }`,
        });
      }
    },
    [
      service,
      refreshCoOwnerData,
      onListRefresh,
      setAlertDetails,
      handleException,
      coOwnerAllUsers,
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
