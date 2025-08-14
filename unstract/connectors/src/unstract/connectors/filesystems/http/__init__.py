from .http import HttpFS

__all__ = ["HttpFS"]

metadata = {
    "name": HttpFS.__name__,
    "version": "1.0.0",
    "connector": HttpFS,
    "description": "HttpFS connector",
    "is_active": False,
}
