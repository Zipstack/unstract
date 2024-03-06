from .azure_cloud_storage import AzureCloudStorageFS

__all__ = ["AzureCloudStorageFS"]


metadata = {
    "name": AzureCloudStorageFS.__name__,
    "version": "1.0.0",
    "connector": AzureCloudStorageFS,
    "description": "AzureCloudStorageFS connector",
    "is_active": True,
}
