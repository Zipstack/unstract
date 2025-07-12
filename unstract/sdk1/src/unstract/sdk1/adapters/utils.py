import logging
import warnings
from pathlib import Path

import filetype
import magic
from requests import Response
from requests.exceptions import RequestException

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.constants import MimeType
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

logger = logging.getLogger(__name__)


class AdapterUtils:
    @staticmethod
    def get_msg_from_request_exc(
        err: RequestException,
        message_key: str,
        default_err: str = Common.DEFAULT_ERR_MESSAGE,
    ) -> str:
        """Gets the message from the RequestException.

        Args:
            err_response (Response): Error response from the exception
            message_key (str): Key from response containing error message

        Returns:
            str: Error message returned by the server
        """
        if not hasattr(err, "response"):
            return default_err

        err_response: Response = err.response  # type: ignore
        err_content_type = err_response.headers.get("Content-Type")

        if not err_content_type:
            logger.warning(
                f"Content-Type header not found in {err_response}, "
                f"returning {default_err}"
            )
            return default_err

        if err_content_type == MimeType.JSON:
            err_json = err_response.json()
            if message_key in err_json:
                return str(err_json[message_key])
            else:
                logger.warning(
                    f"Unable to parse error with key '{message_key}' for "
                    f"'{err_json}', returning '{default_err}' instead."
                )
        elif err_content_type == MimeType.TEXT:
            return err_response.text  # type: ignore
        else:
            logger.warning(
                f"Unhandled err_response type '{err_content_type}' "
                f"for {err_response}, returning {default_err}"
            )
        return default_err

    # TODO: get_file_mime_type() to be removed once migrated to FileStorage
    # FileStorage has mime_type() which could be used instead.
    @staticmethod
    def get_file_mime_type(
        input_file: Path,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        """Gets the file MIME type for an input file. Uses libmagic to perform
        the same.

        Args:
            input_file (Path): Path object of the input file

        Returns:
            str: MIME type of the file
        """
        # Adding the following DeprecationWarning manually as the package "deprecated"
        # does not support deprecation on static methods.
        warnings.warn(
            "`get_file_mime_type` is deprecated. "
            "Use `FileStorage mime_type()` instead.",
            DeprecationWarning,
        )
        sample_contents = fs.read(path=input_file, mode="rb", length=100)
        input_file_mime = magic.from_buffer(sample_contents, mime=True)
        return input_file_mime

    @staticmethod
    def guess_extention(
        input_file_path: str,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        """Returns the extention of the file passed.

        Args:
            input_file_path (str): String holding the path

        Returns:
            str: File extention
        """
        # Adding the following DeprecationWarning manually as the package "deprecated"
        # does not support deprecation on static methods.
        warnings.warn(
            "`guess_extention` is deprecated. "
            "Use `FileStorage guess_extension()` instead.",
            DeprecationWarning,
        )
        input_file_extention = ""
        sample_contents = fs.read(path=input_file_path, mode="rb", length=100)
        if sample_contents:
            file_type = filetype.guess(sample_contents)
            input_file_extention = file_type.EXTENSION
        return input_file_extention
