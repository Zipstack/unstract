"""Contract constants for the global search endpoint: parameter bounds,
match tiers and the OSS type keys. Cloud-only type keys are deliberately
absent: cloud apps define and register their own.
"""

from enum import IntEnum


class SearchParams:
    QUERY = "q"
    TYPES = "types"
    LIMIT = "limit"

    # A shorter query answers an empty result, not an error.
    MIN_QUERY_LENGTH = 2
    MAX_QUERY_LENGTH = 100
    DEFAULT_LIMIT = 5
    MAX_LIMIT = 20


class MatchTier(IntEnum):
    """Ranking tiers, best first. The value is the sort key; the label is
    what the response's ``match`` field carries.
    """

    NAME_PREFIX = 0
    NAME = 1
    DESCRIPTION_PREFIX = 2
    DESCRIPTION = 3

    @property
    def label(self) -> str:
        return self.name.lower()


class OSSSearchType:
    """Type keys contributed by OSS. ``order`` leaves gaps for cloud types."""

    PROMPT_STUDIO_PROJECT = "prompt_studio_project"
    WORKFLOW = "workflow"
    API_DEPLOYMENT = "api_deployment"
    ETL_PIPELINE = "etl_pipeline"
    TASK_PIPELINE = "task_pipeline"
    ADAPTER = "adapter"
    CONNECTOR = "connector"
