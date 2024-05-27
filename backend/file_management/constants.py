class FileInformationKey:
    FILE_NAME = "name"
    FILE_TYPE = "type"
    FILE_LAST_MODIFIED = "LastModified"
    FILE_SIZE = "size"
    FILE_UPLOAD_MAX_SIZE = 100 * 1024 * 1024
    FILE_UPLOAD_ALLOWED_EXT = ["pdf"]
    FILE_UPLOAD_ALLOWED_MIME = ["application/pdf"]


class FileViewTypes:
    ORIGINAL = "ORIGINAL"
    EXTRACT = "EXTRACT"
    SUMMARIZE = "SUMMARIZE"
