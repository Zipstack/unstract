from .google_drive import GoogleDriveFS

__all__ = ["GoogleDriveFS"]

metadata = {
    "name": GoogleDriveFS.__name__,
    "version": "1.0.0",
    "connector": GoogleDriveFS,
    "description": "GoogleDriveFS connector",
    "is_active": True,
}
