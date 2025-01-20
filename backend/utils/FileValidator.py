from collections.abc import Iterable
from os.path import splitext
from typing import Optional, TypedDict

import magic
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _
from typing_extensions import NotRequired, Unpack
from unstract.sdk.file_storage.constants import FileOperationParams


class FileValidationParam(TypedDict):
    allowed_mimetypes: NotRequired[Iterable[str]]
    allowed_extensions: NotRequired[Iterable[str]]
    max_size: NotRequired[int]
    min_size: NotRequired[int]


class FileValidator:
    """Validator for files, checking the size, extension and mimetype.

    Initialization parameters:
        allowed_extensions: iterable with allowed file extensions
            ie. ('txt', 'doc')
        allowed_mimetypes: iterable with allowed mimetypes
            ie. ('image/png', )
        min_size: minimum number of bytes allowed
            ie. 100
        max_size: maximum number of bytes allowed
            ie. 24*1024*1024 for 24 MB
    """

    extension_message = _(
        "Extension '%(extension)s' not allowed. "
        "Allowed extensions are: '%(allowed_extensions)s.'"
    )
    mime_message = _(
        "MIME type '%(mimetype)s' is not valid. "
        "Allowed types are: %(allowed_mimetypes)s."
    )
    min_size_message = _(
        "The current file %(size)s, which is too small. "
        "The minumum file size is %(allowed_size)s."
    )
    max_size_message = _(
        "The current file %(size)s, which is too large. "
        "The maximum file size is %(allowed_size)s."
    )

    def __init__(self, **kwargs: Unpack[FileValidationParam]) -> None:
        self.allowed_extensions: Optional[Iterable[str]] = kwargs.pop(
            "allowed_extensions", None
        )
        self.allowed_mimetypes: Optional[Iterable[str]] = kwargs.pop(
            "allowed_mimetypes", None
        )
        self.min_size: Optional[int] = kwargs.pop("min_size", 0)
        self.max_size: Optional[int] = kwargs.pop("max_size", None)

    def _check_file_extension(self, file: InMemoryUploadedFile) -> None:
        ext = splitext(file.name)[1][1:].lower()
        if self.allowed_extensions and ext not in self.allowed_extensions:
            message = self.extension_message % {
                "extension": ext,
                "allowed_extensions": ", ".join(self.allowed_extensions),
            }

            raise ValidationError(message)

    def _check_file_mime_type(self, file: InMemoryUploadedFile) -> None:
        # TODO: Need to optimise, istead of reading entire file.
        mimetype = magic.from_buffer(
            file.read(FileOperationParams.READ_ENTIRE_LENGTH), mime=True
        )
        file.seek(0)  # Reset the file pointer to the start

        if self.allowed_mimetypes and mimetype not in self.allowed_mimetypes:
            message = self.mime_message % {
                "mimetype": mimetype,
                "allowed_mimetypes": ", ".join(self.allowed_mimetypes),
            }

            raise ValidationError(message)

    def _check_file_size(self, file: InMemoryUploadedFile) -> None:
        filesize = len(file)
        if (self.max_size is not None) and (self.min_size is not None):
            if self.max_size and filesize > self.max_size:
                message = self.max_size_message % {
                    "size": filesizeformat(filesize),
                    "allowed_size": filesizeformat(self.max_size),
                }

                raise ValidationError(message)

            elif filesize < self.min_size:
                message = self.min_size_message % {
                    "size": filesizeformat(filesize),
                    "allowed_size": filesizeformat(self.min_size),
                }

                raise ValidationError(message)

    def __call__(self, value: list[InMemoryUploadedFile]) -> None:
        """Check the extension, content type and file size for each file."""
        for file in value:
            # Check the extension
            self._check_file_extension(file)

            # Check the content type
            self._check_file_mime_type(file)

            # Check the file size
            self._check_file_size(file)
