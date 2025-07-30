"""Constants for Celery backend types"""


class CeleryBackendTypes:
    """Celery backend type constants"""
    POSTGRES = "postgres"
    REDIS = "redis"
    
    CHOICES = [
        (POSTGRES, "PostgreSQL"),
        (REDIS, "Redis"),
    ]
    
    @classmethod
    def is_valid(cls, backend_type):
        """Check if backend type is valid"""
        return backend_type in [cls.POSTGRES, cls.REDIS]