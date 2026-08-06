from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from api_v2.models import APIDeployment

if TYPE_CHECKING:
    from global_api_deployment_key.models import GlobalApiDeploymentKey


@dataclass(frozen=True)
class DeploymentExecutionDTO:
    """DTO for deployment execution viewset.

    Frozen: built once per request in ``DeploymentHelper.validate_api_key`` and
    only read downstream.
    """

    api: APIDeployment
    # repr=False: this is the live bearer credential. Without it the generated
    # __repr__ writes the raw key into any ``logger.debug("...%s", dto)`` or
    # exception repr that touches this object.
    api_key: str = field(repr=False)
    # The global API deployment key that authorized this execution, if any.
    # Carrying the resolved key (not just a bool) preserves audit identity —
    # "which named key authorized this?" — for downstream logging/incidents.
    global_key: "GlobalApiDeploymentKey | None" = None

    @property
    def is_global_key(self) -> bool:
        return self.global_key is not None
