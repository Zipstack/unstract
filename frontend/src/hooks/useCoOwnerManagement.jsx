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
  // "Not applied" rather than "Failed": this list also carries removals that
  // were deliberately skipped because an addition failed first.
  return {
    type: "warning",
    content: `${summary}. Not applied for: ${failedNames}`,
  };
}

/**
 * Run one Apply's add/remove calls. Attempts every user independently --
 * one rejection must not drop the rest or leave the modal contradicting the
 * server.
 */
async function applyCoOwnerMutations(
  service,
  resourceId,
  addUsers,
  removeUsers,
) {
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
  if (failed.length) {
    // The roster never grew, so removing now can strip the very owner the
    // swap was meant to replace. Report them rather than attempt them.
    failed.push(...removeUsers);
  } else {
    await run(removeUsers, (id) => service.removeCoOwner(resourceId, id));
  }
  return { failed, lastError };
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
    // Returns the verdict rather than leaving each caller to re-derive it:
    // "stale" (a later modal superseded this one), "gone" (404), "error"
    // (refresh failed; roster unverified), "ok". "gone" and "error" have both
    // already raised their own alert.
    async (resourceId, requestId = latestRequestRef.current) => {
      try {
        const res = await service.getSharedUsers(resourceId);
        if (latestRequestRef.current !== requestId) {
          return "stale";
        }
        setCoOwnerData({ coOwners: res.data?.co_owners || [] });
        return "ok";
      } catch (err) {
        if (latestRequestRef.current !== requestId) {
          return "stale";
        }
        if (err?.response?.status === 404) {
          setCoOwnerOpen(false);
          onListRefresh?.();
          setAlertDetails({
            type: "error",
            content:
              "This resource is no longer accessible. It may have been removed or your access has been revoked.",
          });
          return "gone";
        }
        setAlertDetails(
          handleException(err, "Unable to refresh co-owner data"),
        );
        return "error";
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

        if (latestRequestRef.current !== requestId) {
          return;
        }

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
        if (latestRequestRef.current !== requestId) {
          return;
        }
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
      const { failed, lastError } = await applyCoOwnerMutations(
        service,
        resourceId,
        addUsers,
        removeUsers,
      );
      // Reconverge on true server state regardless of partial outcome.
      const outcome = await refreshCoOwnerData(resourceId, requestId);
      if (outcome !== "gone") {
        onListRefresh?.(); // page-scoped list; "gone" already refreshed it
      }
      if (outcome === "stale") {
        return false; // another resource is open now, not our modal to alert
      }
      if (outcome === "gone") {
        return true; // refresh already closed the modal and alerted
      }
      // "ok" and "error" both fall through: the mutations landed either way.
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
