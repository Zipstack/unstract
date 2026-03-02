import { useRef, useState } from "react";

/**
 * Shared hook for share modal state and logic.
 * Handles fetching users, opening the modal, and applying share updates.
 *
 * @param {Object} options
 * @param {Object} options.apiService - service with getAllUsers, getSharedUsers, updateSharing
 * @param {Function} options.setSelectedItem - setter for the parent's selected item state
 * @param {Function} options.setAlertDetails - from alert store
 * @param {Function} options.handleException - exception handler
 * @param {Function} options.refreshList - fn() to refresh the list after sharing
 * @return {Object} Share modal state and handlers
 */
function useShareModal({
  apiService,
  setSelectedItem,
  setAlertDetails,
  handleException,
  refreshList,
}) {
  const [openShareModal, setOpenShareModal] = useState(false);
  const [allUsers, setAllUsers] = useState([]);
  const [isLoadingShare, setIsLoadingShare] = useState(false);

  const shareItemIdRef = useRef(null);
  const refreshRef = useRef(refreshList);
  refreshRef.current = refreshList;

  const handleShare = async (item) => {
    shareItemIdRef.current = item.id;
    setIsLoadingShare(true);
    try {
      const [usersResponse, sharedUsersResponse] = await Promise.all([
        apiService.getAllUsers(),
        apiService.getSharedUsers(item.id),
      ]);

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

      setSelectedItem({
        ...item,
        shared_users: Array.isArray(sharedUsersList) ? sharedUsersList : [],
      });
      setAllUsers(userList);
      setOpenShareModal(true);
    } catch (err) {
      setAlertDetails(
        handleException(err, "Unable to fetch sharing information"),
      );
      setAllUsers([]);
    } finally {
      setIsLoadingShare(false);
    }
  };

  const onShare = (sharedUsers, _, shareWithEveryone) => {
    setIsLoadingShare(true);
    apiService
      .updateSharing(shareItemIdRef.current, sharedUsers, shareWithEveryone)
      .then(() => {
        setAlertDetails({
          type: "success",
          content: "Sharing permissions updated successfully",
        });
        setOpenShareModal(false);
        refreshRef.current?.();
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
    isLoadingShare,
    handleShare,
    onShare,
  };
}

export { useShareModal };
