import logging

from plugins import get_plugin

logger = logging.getLogger(__name__)


def notify_hubspot_event(
    user,
    event_name: str,
    is_first_for_org: bool,
    action_label: str,
) -> None:
    """Send a HubSpot event notification if the plugin is available.

    Args:
        user: The user performing the action.
        event_name: The HubSpotEvent attribute name (e.g. "PROMPT_RUN").
        is_first_for_org: Whether this is the first such action for the org.
        action_label: Human-readable label for logging (e.g. "prompt run").
    """
    hubspot_plugin = get_plugin("hubspot")
    if not hubspot_plugin:
        return

    try:
        from plugins.integrations.hubspot import HubSpotEvent

        event = getattr(HubSpotEvent, event_name)
        service = hubspot_plugin["service_class"]()
        service.update_contact(
            user=user,
            events=[event],
            is_first_for_org=is_first_for_org,
        )
    except Exception as e:
        logger.warning(f"Failed to notify HubSpot for {action_label}: {e}")
