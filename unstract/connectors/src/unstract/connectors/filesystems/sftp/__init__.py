from .sftp import SftpFS

__all__ = ["SftpFS"]

metadata = {
    "name": SftpFS.__name__,
    "version": "1.0.0",
    "connector": SftpFS,
    "description": "SftpFS connector",
    "is_active": True,
}
