import tempfile

from django.core.files.uploadedfile import UploadedFile

from unstract.core.mime_gate import classify_file_path


def detect_upload_mime_type(file: UploadedFile) -> str:
    """Classify an upload from its own bytes, as LLMWhisperer would.

    The multipart Content-Type is supplied by the caller and never verified, so
    it cannot decide what is allowed in. Leaves the upload rewound.
    """
    temporary_file_path = getattr(file, "temporary_file_path", None)
    if temporary_file_path is not None:
        return classify_file_path(temporary_file_path())

    with tempfile.NamedTemporaryFile(suffix=".upload") as spill:
        file.seek(0)
        for chunk in file.chunks():
            spill.write(chunk)
        spill.flush()
        file.seek(0)
        return classify_file_path(spill.name)
