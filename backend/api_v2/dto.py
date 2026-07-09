from dataclasses import dataclass
from typing import TYPE_CHECKING

from api_v2.models import APIDeployment

if TYPE_CHECKING:
    from global_api_deployment_key.models import GlobalApiDeploymentKey


@dataclass
class DeploymentExecutionDTO:
    """DTO for deployment execution viewset."""

    api: APIDeployment
    api_key: str
    # The global API deployment key that authorized this execution, if any.
    # Carrying the resolved key (not just a bool) preserves audit identity —
    # "which named key authorized this?" — for downstream logging/incidents.
    global_key: "GlobalApiDeploymentKey | None" = None

    @property
    def is_global_key(self) -> bool:
        return self.global_key is not None
