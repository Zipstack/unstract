from .zs_dropbox import DropboxFS

__all__ = ["DropboxFS"]


metadata = {
    "name": DropboxFS.__name__,
    "version": "1.0.0",
    "connector": DropboxFS,
    "description": "DropboxFS connector",
    "is_active": True,
}
