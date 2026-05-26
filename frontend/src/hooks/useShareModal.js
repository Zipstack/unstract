import { useRef, useState } from "react";

/**
 * Shared hook for share modal state and logic.
 * Handles fetching users + groups, opening the modal, and applying share updates.
 *
 * ``apiService.updateSharing`` may accept an optional fourth ``sharedGroups``
 * argument — services that don't support groups yet are unaffected.
 *
 * @param {Object} options
 * @param {Object} options.apiService - service with getAllUsers, getSharedUsers, updateSharing
 * @param {Object} [options.groupsApi] - optional service exposing listGroups(); when present, group sharing is enabled
 * @param {Function} options.setSelectedItem - setter for the parent's selected item state
 * @param {Function} options.setAlertDetails - from alert store
 * @param {Function} options.handleException - exception handler
 * @param {Function} options.refreshList - fn() to refresh the list after sharing
 * @return {Object} Share modal state and handlers
 */
function useShareModal({
  apiService,
  groupsApi,
  setSelectedItem,
  setAlertDetails,
  handleException,
  refreshList,
}) {
  const [openShareModal, setOpenShareModal] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [allGroups, setAllGroups] = useState([]);
  const [isLoadingShare, setIsLoadingShare] = useState(false);

  const shareItemIdRef = useRef(null);
  const refreshRef = useRef(refreshList);
  refreshRef.current = refreshList;

  const handleShare = async (item) => {
    shareItemIdRef.current = item.id;
    setIsLoadingShare(true);
    try {
      const calls = [
        apiService.getAllUsers(),
        apiService.getSharedUsers(item.id),
      ];
      if (groupsApi?.listGroups) {
        calls.push(groupsApi.listGroups());
      }
      const [usersResponse, sharedUsersResponse, groupsResponse] =
        await Promise.all(calls);

      let userList = [];
      const responseData = usersResponse?.data;
      if (Array.isArray(responseData)) {
        userList = responseData.map((user) => ({
          id: user.id,
          email: user.email,
        }));
      } else if (responseData?.members && Array.isArray(responseData.members)) {
        userList = responseData.members.map((member) => ({
          id: member.id,
          email: member.email,
        }));
      } else if (responseData?.users && Array.isArray(responseData.users)) {
        userList = responseData.users.map((user) => ({
          id: user.id,
          email: user.email,
        }));
      }

      const sharedUsersList = sharedUsersResponse.data?.shared_users || [];
      const sharedGroupsList = sharedUsersResponse.data?.shared_groups || [];

      setSelectedItem({
        ...item,
        shared_users: Array.isArray(sharedUsersList) ? sharedUsersList : [],
        shared_groups: Array.isArray(sharedGroupsList) ? sharedGroupsList : [],
      });
      setAllUsers(userList);
      const groupItems = Array.isArray(groupsResponse?.data)
        ? groupsResponse.data
        : [];
      setAllGroups(
        groupItems.map((g) => ({
          id: g.id,
          name: g.name,
        })),
      );
      setOpenShareModal(true);
    } catch (err) {
      setAlertDetails(
        handleException(err, "Unable to fetch sharing information"),
      );
      setAllUsers([]);
      setAllGroups([]);
    } finally {
      setIsLoadingShare(false);
    }
  };

  const onShare = (sharedUsers, _, shareWithEveryone, sharedGroups) => {
    setIsLoadingShare(true);
    apiService
      .updateSharing(
        shareItemIdRef.current,
        sharedUsers,
        shareWithEveryone,
        sharedGroups || [],
      )
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Sharing permissions updated successfully",
        });
        refreshRef.current?.();
        // Close only on success; keep the modal open on failure so the user
        // can see the rejected entries and retry.
        setOpenShareModal(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsLoadingShare(false);
      });
  };

  return {
    openShareModal,
    setOpenShareModal,
    allUsers,
    allGroups,
    isLoadingShare,
    handleShare,
    onShare,
  };
}

export { useShareModal };
