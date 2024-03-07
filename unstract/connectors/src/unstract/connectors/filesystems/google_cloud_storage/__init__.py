from .google_cloud_storage import GoogleCloudStorageFS

__all__ = ["GoogleCloudStorageFS"]


metadata = {
    "name": GoogleCloudStorageFS.__name__,
    "version": "1.0.0",
    "connector": GoogleCloudStorageFS,
    "description": "GoogleCloudStorageFS connector",
    "is_active": True,
}
