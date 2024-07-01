import logging

from unstract.flags.client.flipt import FliptClient
from unstract.flags.feature_flag import check_feature_flag_status

logger = logging.getLogger(
    __name__,
)


class FeatureFlagHelper:
    @staticmethod
    def list_all_flags(
        namespace_key: str,
    ) -> dict:
        """Fetch all flags from flipt.

        Args:
            namespace_key (str)

        Returns:
            dict
        """
        try:
            flipt_client = FliptClient()
            response = flipt_client.list_feature_flags(
                namespace_key=namespace_key,
            )
            return response
        except Exception as e:
            logger.error(
                f"Error while listing flags for namespace {namespace_key}: {str(e)}"
            )
            return {}

    @staticmethod
    def check_flag_status(
        flag_name: str,
    ) -> bool:
        """Check current status of flag
        Args:
            flag_name (str): feature flag

        Returns:
            bool: is active or not
        """
        flag_enabled = check_feature_flag_status(flag_name)
        return flag_enabled
