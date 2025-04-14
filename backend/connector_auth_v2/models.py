import logging
import uuid
from typing import Any

from account_v2.models import User
from django.db import models
from django.db.models.query import QuerySet
from rest_framework.request import Request
from social_django.fields import JSONField
from social_django.models import AbstractUserSocialAuth, DjangoStorage
from social_django.strategy import DjangoStrategy

from connector_auth_v2.constants import SocialAuthConstants
from connector_auth_v2.pipeline.google import GoogleAuthHelper

logger = logging.getLogger(__name__)


class ConnectorAuthManager(models.Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        # TODO PAN-83: Decrypt here
        # for obj in queryset:
        #     logger.info(f"Decrypting extra_data: {obj.extra_data}")

        return queryset


class ConnectorAuth(AbstractUserSocialAuth):
    """Social Auth association model, stores tokens.
    The relation with `account.User` is only for the library to work
    and should be NOT be used to access the secrets.
    Use the following static methods instead
    ```
        @classmethod
        def get_social_auth(cls, provider, id):

        @classmethod
        def create_social_auth(cls, user, uid, provider):
    ```
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        related_name="connector_auths",
        on_delete=models.CASCADE,
        null=True,
    )

    def __str__(self) -> str:
        return f"ConnectorAuth(provider: {self.provider}, uid: {self.uid})"

    def save(self, *args: Any, **kwargs: Any) -> Any:
        # TODO PAN-83: Encrypt here
        # logger.info(f"Encrypting extra_data: {self.extra_data}")
        return super().save(*args, **kwargs)

    def set_extra_data(self, extra_data=None):  # type: ignore
        ConnectorAuth.check_credential_format(extra_data)
        if extra_data[SocialAuthConstants.PROVIDER] == SocialAuthConstants.GOOGLE_OAUTH:
            extra_data = GoogleAuthHelper.enrich_connector_metadata(extra_data)
        return super().set_extra_data(extra_data)

    def refresh_token(self, strategy, *args, **kwargs):  # type: ignore
        """Override of Python Social Auth (PSA)'s refresh_token functionality
        to store uid, provider.
        """
        token = self.extra_data.get("refresh_token") or self.extra_data.get(
            "access_token"
        )
        backend = self.get_backend_instance(strategy)
        if token and backend and hasattr(backend, "refresh_token"):
            response = backend.refresh_token(token, *args, **kwargs)
            extra_data = backend.extra_data(self, self.uid, response, self.extra_data)
            extra_data[SocialAuthConstants.PROVIDER] = backend.name
            extra_data[SocialAuthConstants.UID] = self.uid
            if self.set_extra_data(extra_data):  # type: ignore
                self.save()

    def get_and_refresh_tokens(self, request: Request = None) -> tuple[JSONField, bool]:
        """Uses Social Auth's ability to refresh tokens if necessary.

        Returns:
            Tuple[JSONField, bool]: JSONField of connector metadata
            and flag indicating if tokens were refreshed
        """
        # To avoid circular dependency error on import
        from social_django.utils import load_strategy

        refreshed_token = False
        strategy: DjangoStrategy = load_strategy(request=request)
        existing_access_token = self.access_token
        new_access_token = self.get_access_token(strategy)
        if new_access_token != existing_access_token:
            refreshed_token = True
            related_connector_instances = self.connectorinstance_set.all()
            for connector_instance in related_connector_instances:
                connector_instance.connector_metadata = self.extra_data
                connector_instance.save()
                logger.info(
                    f"Refreshed access token for connector {connector_instance.id}, "
                    f"provider: {self.provider}, uid: {self.uid}"
                )

        return self.extra_data, refreshed_token

    @staticmethod
    def check_credential_format(
        oauth_credentials: dict[str, str], raise_exception: bool = True
    ) -> bool:
        if (
            SocialAuthConstants.PROVIDER in oauth_credentials
            and SocialAuthConstants.UID in oauth_credentials
        ):
            return True
        else:
            if raise_exception:
                raise ValueError(
                    "Auth credential should have provider, uid and connector guid"
                )
            return False

    objects = ConnectorAuthManager()

    class Meta:
        app_label = "connector_auth_v2"
        verbose_name = "Connector Auth"
        verbose_name_plural = "Connector Auths"
        db_table = "connector_auth"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "provider",
                    "uid",
                ],
                name="unique_provider_uid_index",
            ),
        ]


class ConnectorDjangoStorage(DjangoStorage):
    user = ConnectorAuth
