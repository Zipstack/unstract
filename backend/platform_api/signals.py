import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from platform_api.models import PlatformApiKey
from platform_api.services import delete_api_user_for_key

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=PlatformApiKey)
def cleanup_api_user_on_key_delete(sender, instance, **kwargs):
    """Ensure service account is cleaned up when a key is deleted via any path."""
    try:
        delete_api_user_for_key(instance)
    except Exception:
        logger.exception(
            "Failed to clean up service account for key %s — "
            "service account may be orphaned",
            instance.id,
        )
