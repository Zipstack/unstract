from .minio import MinioFS

__all__ = ["MinioFS"]

metadata = {
    "name": MinioFS.__name__,
    "version": "1.0.0",
    "connector": MinioFS,
    "description": "MinioFS connector",
    "is_active": True,
}
