from .sharepoint import SharePointFS

__all__ = ["SharePointFS"]

metadata = {
    "name": SharePointFS.__name__,
    "version": "1.0.0",
    "connector": SharePointFS,
    "description": "SharePoint/OneDrive connector for document libraries and cloud storage",
    "is_active": True,
}
