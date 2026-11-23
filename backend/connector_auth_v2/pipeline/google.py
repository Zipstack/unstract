from datetime import datetime, timedelta

from connector_auth_v2.constants import SocialAuthConstants as AuthConstants
from connector_auth_v2.exceptions import EnrichConnectorMetadataException
from connector_processor.constants import ConnectorKeys
from unstract.connectors.filesystems.google_drive.constants import GDriveConstants


class GoogleAuthHelper:
    @staticmethod
    def enrich_connector_metadata(kwargs: dict[str, str]) -> dict[str, str]:
        token_expiry: datetime = datetime.now()
        auth_time = kwargs.get(AuthConstants.AUTH_TIME)
        expires = kwargs.get(AuthConstants.EXPIRES)
        if auth_time and expires:
            reference = datetime.utcfromtimestamp(float(auth_time))
            token_expiry = reference + timedelta(seconds=float(expires))
        else:
            raise EnrichConnectorMetadataException
        # Used by GDrive FS, apart from ACCESS_TOKEN and REFRESH_TOKEN
        kwargs[GDriveConstants.TOKEN_EXPIRY] = token_expiry.strftime(
            AuthConstants.GOOGLE_TOKEN_EXPIRY_FORMAT
        )

        # Used by Unstract
        kwargs[ConnectorKeys.PATH] = (
            GDriveConstants.ROOT_PREFIX
        )  # Acts as a prefix for all paths
        kwargs[AuthConstants.REFRESH_AFTER] = token_expiry.strftime(
            AuthConstants.REFRESH_AFTER_FORMAT
        )
        return kwargs
