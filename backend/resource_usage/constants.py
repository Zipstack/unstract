from enum import StrEnum


class UsageGroup(StrEnum):
    """Groups every usage response carries, even when empty.

    The cloud backend may add further groups (see ``references.register_provider``).
    """

    WORKFLOWS = "workflows"
    PROMPT_STUDIO_PROJECTS = "prompt_studio_projects"
    DEPLOYMENTS = "deployments"
    PIPELINES = "pipelines"


# References the delete guard refuses on that no group claims.
OTHER_GROUP = "other"


class ItemType(StrEnum):
    """What a usage item is, so the frontend knows where it routes."""

    WORKFLOW = "workflow"
    PROMPT_STUDIO_PROJECT = "prompt_studio_project"
    PROMPT_STUDIO_PROFILE = "prompt_studio_profile"
    API_DEPLOYMENT = "api_deployment"
    PIPELINE = "pipeline"


class ConnectorRole(StrEnum):
    SOURCE = "source"
    DESTINATION = "destination"
    BOTH = "both"


class UsedAs(StrEnum):
    """The roles a connector plays across everything that uses it."""

    SOURCE = "source"
    DESTINATION = "destination"
    BOTH = "both"
    NONE = "none"


class ProfileKind(StrEnum):
    ADAPTER = "adapter"
    CONNECTOR = "connector"


class ListParam:
    """Optional list query parameters and the keys they add."""

    WITH_USAGE = "with_usage"
    UNUSED = "unused"
    USED_IN_COUNT = "used_in_count"
    USED_AS = "used_as"
    UNUSED_COUNT = "unused_count"
