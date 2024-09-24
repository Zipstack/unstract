class FileInformationKey:
    FILE_NAME = "name"
    FILE_TYPE = "type"
    FILE_LAST_MODIFIED = "LastModified"
    FILE_SIZE = "size"
    FILE_UPLOAD_MAX_SIZE = 100 * 1024 * 1024
    FILE_UPLOAD_ALLOWED_EXT = [
        "pdf",
        "jpg",
        "jpeg",
        "png",
        "doc",
        "docx",
        "gif",
        "bmp",
        "tif",
        "tiff",
        "txt",
    ]  # Added image and doc extensions
    FILE_UPLOAD_ALLOWED_MIME = [
        "application/pdf",  # PDF
        "image/jpeg",  # JPEG images
        "image/png",  # PNG images
        "application/msword",  # DOC (Word)
        "application/vnd.openxmlformats-officedocument.wordprocessingml."
        "document",  # DOCX (Word)
    ]


class FileViewTypes:
    ORIGINAL = "ORIGINAL"
    EXTRACT = "EXTRACT"
    SUMMARIZE = "SUMMARIZE"
