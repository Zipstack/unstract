import os
import sys

from dotenv import load_dotenv

load_dotenv()


# Check if gevent patches were applied early
def should_apply_gevent():
    """Determine if we should apply gevent patches.

    Only apply patches when:
    1. CELERY_POOL=gevent is set
    2. We're running as a Celery worker
    3. We're not running Django server commands
    """
    if os.environ.get("CELERY_POOL") != "gevent":
        return False

    # Check if we're running as a Celery worker
    argv_str = " ".join(sys.argv)
    is_celery_worker = "celery" in sys.argv[0] and "worker" in argv_str

    # Don't patch Django processes
    is_django_process = any(
        cmd in argv_str for cmd in ["runserver", "gunicorn", "manage.py"]
    )

    return is_celery_worker and not is_django_process


if should_apply_gevent():
    import logging

    logger = logging.getLogger(__name__)
    logger.info("Gevent patches should be applied via gevent_init module")

    # CRITICAL: Patch Unstract SDK to use our pure boto3 implementation
    def patch_unstract_sdk_for_gevent():
        """Patch Unstract SDK FileStorageHelper to use pure boto3 for MINIO/S3."""
        try:
            from unstract.connectors.filesystems.minio.minio import Boto3S3FileSystem
            from unstract.sdk.file_storage.helper import FileStorageHelper
            from unstract.sdk.file_storage.provider import FileStorageProvider

            # Store the original method
            original_file_storage_init = FileStorageHelper.file_storage_init

            @staticmethod
            def gevent_file_storage_init(provider: FileStorageProvider, **storage_config):
                """Gevent-compatible version of file_storage_init."""
                # If provider is MINIO and we're in gevent mode, return our pure boto3 implementation
                if (
                    provider == FileStorageProvider.MINIO
                    and os.environ.get("CELERY_POOL") == "gevent"
                ):
                    try:
                        logger.info(
                            f"SDK: Using pure boto3 for gevent - provider={provider}"
                        )

                        # Create pure boto3 filesystem directly
                        return Boto3S3FileSystem(
                            key=storage_config.get("key", ""),
                            secret=storage_config.get("secret", ""),
                            endpoint_url=storage_config.get("endpoint_url", ""),
                            client_kwargs=storage_config.get("client_kwargs", {}),
                        )

                    except Exception as e:
                        logger.warning(f"Failed to create pure boto3 SDK filesystem: {e}")
                        # Fall back to original method
                        pass

                # For all other cases, use the original method
                return original_file_storage_init(provider, **storage_config)

            # Replace the method
            FileStorageHelper.file_storage_init = gevent_file_storage_init
            logger.info("Patched Unstract SDK FileStorageHelper for gevent compatibility")

        except Exception as e:
            logger.warning(f"Could not patch Unstract SDK: {e}")

    # Apply SDK patch
    patch_unstract_sdk_for_gevent()

    # Verify patching worked
    try:
        import socket

        if hasattr(socket, "_original_socket"):
            logger.debug("Socket patching confirmed")
    except Exception:
        pass
else:
    import logging

    logger = logging.getLogger(__name__)
    env_pool = os.environ.get("CELERY_POOL", "not set")
    argv_info = f"argv[0]: {sys.argv[0] if sys.argv else 'none'}"
    logger.debug(f"Gevent patches NOT applied - CELERY_POOL={env_pool}, {argv_info}")

from .celery_service import app as celery_app  # noqa: E402

__all__ = ["celery_app"]
