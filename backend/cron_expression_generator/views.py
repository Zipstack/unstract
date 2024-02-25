import logging

from cron_expression_generator.constants import CronKeys
from cron_expression_generator.descriptor import CronDescriptor
from cron_expression_generator.exceptions import (
    CronDescriptionError,
    CronGenerationError,
)
from cron_expression_generator.generator import CronGenerator
from cron_expression_generator.serializer import CronGenerateSerializer
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

logger = logging.getLogger(__name__)


class CronViewSet(viewsets.GenericViewSet, viewsets.mixins.CreateModelMixin):
    versioning_class = URLPathVersioning
    serializer_class = CronGenerateSerializer

    def generate(self, request: Request) -> Response:
        """For an input of `frequency`, generates the cron string and summary.

        For an input of `cron_string`, generates the summary alone.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        frequency_from_user = serializer.validated_data.get(CronKeys.FREQUENCY)
        cron_string = serializer.validated_data.get(CronKeys.CRON_STRING)
        if frequency_from_user:
            cache_key_prefix = request.org_id
            try:
                cron_string = CronGenerator.generate_cron(
                    frequency=frequency_from_user, cache_key_prefix=cache_key_prefix
                )
                serializer.validated_data[CronKeys.CRON_STRING] = cron_string
            except Exception as e:
                logger.error(
                    f"Error generating cron for input: '{frequency_from_user}'"
                    f", error: {e}"
                )
                raise CronGenerationError()

        if cron_string:
            try:
                serializer.validated_data[
                    CronKeys.SUMMARY
                ] = CronDescriptor.describe_cron(cron=cron_string)
            except Exception as e:
                logger.error(
                    f"Error describing cron for input: '{cron_string}', error: {e}"
                )
                raise CronDescriptionError()
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

    def clear_cron_cache(self, request: Request) -> Response:
        """Clears the cache used for cron generation."""
        cache_key_prefix = request.query_params.get(CronKeys.ORG_ID, request.org_id)
        is_cleared = CronGenerator.clear_cron_cache(cache_key_prefix=cache_key_prefix)
        return Response(
            {CronKeys.CRON_CACHE_STATUS: is_cleared}, status=status.HTTP_200_OK
        )
