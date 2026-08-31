import { useCallback, useRef, useState } from "react";

import { useExceptionHandler } from "./useExceptionHandler";

/**
 * Summarize one Apply into a single alert.
 *
 * Failures carry the user object rather than the id, so an owner who has since
 * left the org — and is therefore missing from the org member list — is still
 * named by email.
 */
function buildApplyAlert(
  addUsers,
  removeUsers,
  failed,
  lastError,
  handleException,
) {
  const total = addUsers.length + removeUsers.length;
  if (failed.length === total) {
    return handleException(lastError, "Unable to update co-owners");
  }
  const failedIds = new Set(failed.map((user) => String(user?.id)));
  const done = (users) =>
    users.filter((user) => !failedIds.has(String(user?.id))).length;
  const parts = [];
  if (done(addUsers)) {
    parts.push(`${done(addUsers)} added`);
  }
  if (done(removeUsers)) {
    parts.push(`${done(removeUsers)} removed`);
  }
  const summary = `Co-owners updated: ${parts.join(", ")}`;
  if (failed.length === 0) {
    return { type: "success", content: summary };
  }
  const failedNames = failed.map((user) => user?.email || user?.id).join(", ");
  return { type: "warning", content: `${summary}. Failed for: ${failedNames}` };
}

function useCoOwnerManagement({ service, setAlertDetails, onListRefresh }) {
  const handleException = useExceptionHandler();

  const [coOwnerOpen, setCoOwnerOpen] = useState(false);
  const [coOwnerData, setCoOwnerData] = useState({ coOwners: [] });
  const [coOwnerLoading, setCoOwnerLoading] = useState(false);
  const [coOwnerAllUsers, setCoOwnerAllUsers] = useState([]);
  const [coOwnerResourceId, setCoOwnerResourceId] = useState(null);
  const latestRequestRef = useRef(null);

  const refreshCoOwnerData = useCallback(
    // Bail if another modal open superseded this refresh — a slow response
    // must not commit a stale roster (or close a healthy modal via the 404
    // branch) after the user has moved to a different resource. Mutation
    // callers pass the token captured BEFORE their POSTs so a modal switch
    // during the mutation itself is caught too, not just one mid-refresh.
    // Returns true when the resource turned out to be gone, so the caller can
    // leave that alert standing instead of overwriting it with its own.
    async (resourceId, requestId = latestRequestRef.current) => {
      try {
        const res = await service.getSharedUsers(resourceId);
        if (latestRequestRef.current !== requestId) return;
        setCoOwnerData({ coOwners: res.data?.co_owners || [] });
      } catch (err) {
        if (latestRequestRef.current !== requestId) return;
        if (err?.response?.status === 404) {
          setCoOwnerOpen(false);
          onListRefresh?.();
          setAlertDetails({
            type: "error",
            content:
              "This resource is no longer accessible. It may have been removed or your access has been revoked.",
          });
          return true;
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

  const onApplyCoOwners = useCallback(
    async (resourceId, { addUsers = [], removeUsers = [] }) => {
      const requestId = latestRequestRef.current;
      // Attempt every user independently — one rejection must not drop the rest
      // or leave the modal contradicting the server.
      const failed = [];
      let lastError = null;
      const run = async (users, call) => {
        for (const user of users) {
          try {
            await call(user.id);
          } catch (err) {
            failed.push(user);
            lastError = err;
          }
        }
      };
      // Adds first: the backend rejects removing the last owner, so a one-shot
      // owner swap has to grow the roster before it shrinks it.
      await run(addUsers, (id) => service.addCoOwner(resourceId, id));
      await run(removeUsers, (id) => service.removeCoOwner(resourceId, id));
      // Reconverge the modal on true server state regardless of partial outcome.
      const gone = await refreshCoOwnerData(resourceId, requestId);
      if (gone) {
        // The refresh already closed the modal, refreshed the list and raised
        // its own alert — an apply summary on top of it would only mislead.
        return true;
      }
      onListRefresh?.();
      setAlertDetails(
        buildApplyAlert(
          addUsers,
          removeUsers,
          failed,
          lastError,
          handleException,
        ),
      );
      return failed.length === 0;
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
    onApplyCoOwners,
  };
}

export { useCoOwnerManagement };
