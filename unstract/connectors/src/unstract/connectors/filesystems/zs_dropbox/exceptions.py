from dropbox.auth import AuthError
from dropbox.exceptions import ApiError
from dropbox.exceptions import AuthError as ExcAuthError
from dropbox.exceptions import DropboxException

from unstract.connectors.exceptions import ConnectorError


def handle_dropbox_exception(e: DropboxException) -> ConnectorError:
    user_msg = "Error from Dropbox while testing connection: "
    if isinstance(e, ExcAuthError):
        if isinstance(e.error, AuthError):
            if e.error.is_expired_access_token():
                user_msg += (
                    "Expired access token, please regenerate it "
                    "through the Dropbox console."
                )
            elif e.error.is_invalid_access_token():
                user_msg += (
                    "Invalid access token, please enter a valid token "
                    "from the Dropbox console."
                )
            else:
                user_msg += e.error._tag
    elif isinstance(e, ApiError):
        if e.user_message_text is not None:
            user_msg += e.user_message_text
    return ConnectorError(message=user_msg, treat_as_user_message=True)
