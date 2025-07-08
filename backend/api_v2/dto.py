from dataclasses import dataclass

from api_v2.models import APIDeployment


@dataclass
class DeploymentExecutionDTO:
    """DTO for deployment execution viewset."""

    api: APIDeployment
    api_key: str
