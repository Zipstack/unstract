import logging

from api.exceptions import Forbidden, UnauthorizedKey
from api.models import APIDeployment, APIKey
from api.serializers import APIKeySerializer
from workflow_manager.workflow.workflow_helper import WorkflowHelper

logger = logging.getLogger(__name__)


class KeyHelper:
    @staticmethod
    def validate_api_key(api_key: str, api_instance: APIDeployment) -> None:
        """Validate api key.

        Args:
            api_key (str): api key from request
            api_instance (APIDeployment): api deployment instance

        Raises:
            Forbidden: _description_
        """
        try:
            api_key_instance: APIKey = APIKey.objects.get(api_key=api_key)
            if not KeyHelper.has_access(api_key_instance, api_instance):
                raise UnauthorizedKey()
        except APIKey.DoesNotExist:
            raise UnauthorizedKey()
        except APIDeployment.DoesNotExist:
            raise Forbidden("API not found.")

    @staticmethod
    def list_api_keys_of_api(api_instance: APIDeployment) -> list[APIKey]:
        api_keys: list[APIKey] = APIKey.objects.filter(api=api_instance).all()
        return api_keys

    @staticmethod
    def has_access(api_key: APIKey, api_instance: APIDeployment) -> bool:
        """Check if the provided API key has access to the specified API
        instance.

        Args:
            api_key (APIKey): api key associated with the api
            api_instance (APIDeployment): api model

        Returns:
            bool: True if allowed to execute, False otherwise
        """
        if not api_key.is_active:
            return False
        if isinstance(api_key.api, APIDeployment):
            return api_key.api == api_instance
        return False

    @staticmethod
    def validate_workflow_exists(workflow_id: str) -> None:
        """Validate that the specified workflow_id exists in the Workflow
        model."""
        WorkflowHelper.get_workflow_by_id(workflow_id)

    @staticmethod
    def create_api_key(deployment: APIDeployment) -> APIKey:
        """Create an APIKey entity with the data from the provided
        APIDeployment instance."""
        # Create an instance of the APIKey model
        api_key_serializer = APIKeySerializer(
            data={"api": deployment.id, "description": "Initial Access Key"},
            context={"deployment": deployment},
        )
        api_key_serializer.is_valid(raise_exception=True)
        api_key: APIKey = api_key_serializer.save()
        return api_key
