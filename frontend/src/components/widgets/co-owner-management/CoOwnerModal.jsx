import PropTypes from "prop-types";

import { CoOwnerManagement } from "./CoOwnerManagement";

/**
 * Thin wrapper that maps a `useCoOwnerManagement()` bag plus `resourceType`
 * onto the CoOwnerManagement modal, so resource list pages don't each repeat
 * the identical prop wiring.
 *
 * @param {Object} props
 * @param {Object} props.coOwner - The `useCoOwnerManagement()` return value.
 * @param {string} props.resourceType - Human-readable resource label.
 * @return {JSX.Element}
 */
function CoOwnerModal({ coOwner, resourceType }) {
  return (
    <CoOwnerManagement
      open={coOwner.coOwnerOpen}
      setOpen={coOwner.setCoOwnerOpen}
      resourceId={coOwner.coOwnerResourceId}
      resourceType={resourceType}
      allUsers={coOwner.coOwnerAllUsers}
      coOwners={coOwner.coOwnerData.coOwners}
      createdBy={coOwner.coOwnerData.createdBy}
      loading={coOwner.coOwnerLoading}
      onAddCoOwner={coOwner.onAddCoOwner}
      onRemoveCoOwner={coOwner.onRemoveCoOwner}
    />
  );
}

CoOwnerModal.propTypes = {
  coOwner: PropTypes.object.isRequired,
  resourceType: PropTypes.string.isRequired,
};

export { CoOwnerModal };
