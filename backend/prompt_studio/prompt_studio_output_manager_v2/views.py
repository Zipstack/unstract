import logging
import uuid
from typing import Any

from account_v2.models import Organization
from django.db.models import QuerySet
from django.http import HttpRequest
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.common_utils import CommonUtils
from utils.filtering import FilterHelper
from utils.user_context import UserContext
from utils.uuid_validation import validated_uuid

from prompt_studio.prompt_studio_output_manager_v2.constants import (
    PromptOutputManagerErrorMessage,
    PromptStudioOutputManagerKeys,
)
from prompt_studio.prompt_studio_output_manager_v2.output_manager_helper import (
    OutputManagerHelper,
)
from prompt_studio.prompt_studio_output_manager_v2.serializers import (
    PromptStudioOutputSerializer,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

from .models import PromptStudioOutputManager

logger = logging.getLogger(__name__)


def _required_organization(tool_id: uuid.UUID) -> Organization:
    """The request's organization, refusing to proceed without one.

    ``UserContext.get_organization()`` returns None on both
    ``Organization.DoesNotExist`` and ``ProgrammingError``, neither logged. A
    None here compiles to ``organization_id IS NULL``, which matches only rows
    whose organization was never set and never the caller's tool — downstream
    every output renders as ``""`` and the user sees a blank project that has
    real persisted outputs, with nothing to correlate in logs. These endpoints
    are only routed under ``/api/v1/unstract/<org>/``, so a null org is a bug,
    not a state to serve.
    """
    organization = UserContext.get_organization()
    if organization is None:
        logger.error(
            "No organization in context while reading prompt-studio outputs "
            "(tool %s); refusing to serve an unscoped empty result.",
            tool_id,
        )
        raise APIException(detail="Organization context is unavailable.")
    return organization


class PromptStudioOutputView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = PromptStudioOutputSerializer

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
            PromptStudioOutputManagerKeys.PROMPT_ID,
            PromptStudioOutputManagerKeys.PROFILE_MANAGER,
            PromptStudioOutputManagerKeys.DOCUMENT_MANAGER,
            PromptStudioOutputManagerKeys.IS_SINGLE_PASS_EXTRACT,
        )

        # Get the query parameter for "is_single_pass_extract"
        is_single_pass_extract_param = self.request.GET.get(
            PromptStudioOutputManagerKeys.IS_SINGLE_PASS_EXTRACT, "false"
        )

        # Same 500-on-bad-UUID as the detail actions: build_filter_args copies
        # query params straight through, and all four of these are UUID
        # columns, so `?tool_id=abc` raises while the query is being built.
        for key in (
            PromptStudioOutputManagerKeys.TOOL_ID,
            PromptStudioOutputManagerKeys.PROMPT_ID,
            PromptStudioOutputManagerKeys.PROFILE_MANAGER,
            PromptStudioOutputManagerKeys.DOCUMENT_MANAGER,
        ):
            if key in filter_args:
                filter_args[key] = validated_uuid(filter_args[key], key)

        # Convert the string representation to a boolean value
        is_single_pass_extract = CommonUtils.str_to_bool(is_single_pass_extract_param)

        filter_args[PromptStudioOutputManagerKeys.IS_SINGLE_PASS_EXTRACT] = (
            is_single_pass_extract
        )

        if filter_args:
            queryset = PromptStudioOutputManager.objects.filter(**filter_args)
        else:
            queryset = PromptStudioOutputManager.objects.all()

        return queryset

    def latest_outputs_by_keys(self, request: HttpRequest) -> Response:
        """Return the most recent raw output value per source prompt key.

        Backs the lookup Test panel's "Use Latest Outputs" button. Returns
        raw extraction (not enriched) so the lookup can be tested fresh.
        """
        tool_id = request.GET.get("tool_id")
        keys_param = request.GET.get("prompt_keys", "")
        if not tool_id:
            # APIException(code=400) returns 500; ValidationError returns 400.
            raise ValidationError(detail=PromptOutputManagerErrorMessage.TOOL_VALIDATION)

        prompt_keys = [k.strip() for k in keys_param.split(",") if k.strip()]
        if not prompt_keys:
            return Response({}, status=status.HTTP_200_OK)

        tool_id = validated_uuid(tool_id, PromptStudioOutputManagerKeys.TOOL_ID)

        # Defence in depth, not the only scope. Since these models moved to
        # OrgAwareManager (pinned to tool_id__organization in
        # ORG_PATH_OVERRIDES) the manager appends this same predicate on its
        # own, resolving the org through the same UserContext call
        # _required_organization() makes. Kept explicit because a raw .objects
        # query is not routed through filter_queryset(), so the view layer
        # contributes nothing here and the manager pin would be the single
        # point of failure. test_cross_org_isolation pins the manager
        # independently, so removing these kwargs stays a safe follow-up.
        organization = _required_organization(tool_id)
        prompt_id_to_key = dict(
            ToolStudioPrompt.objects.filter(
                tool_id=tool_id,
                tool_id__organization=organization,
                prompt_key__in=prompt_keys,
            ).values_list("prompt_id", "prompt_key")
        )
        if not prompt_id_to_key:
            return Response({}, status=status.HTTP_200_OK)

        # ``DISTINCT ON("prompt_id")`` keeps the latest row per prompt at
        # the SQL layer to avoid materialising every doc × run combo.
        outputs = (
            PromptStudioOutputManager.objects.filter(
                prompt_id__in=prompt_id_to_key.keys(),
                tool_id__organization=organization,
            )
            .exclude(output__isnull=True)
            .exclude(output__exact="")
            .order_by("prompt_id", "-modified_at")
            .distinct("prompt_id")
            .values("prompt_id", "output")
        )

        result: dict[str, str] = {}
        for row in outputs:
            key = prompt_id_to_key.get(row["prompt_id"])
            if key:
                result[key] = row["output"]

        return Response(result, status=status.HTTP_200_OK)

    def get_output_for_tool_default(self, request: HttpRequest) -> Response:
        # Get the tool_id from request parameters
        # TODO: Setup Serializer here
        tool_id = request.GET.get("tool_id")
        document_manager_id = request.GET.get("document_manager")
        tool_validation_message = PromptOutputManagerErrorMessage.TOOL_VALIDATION
        if not tool_id:
            raise ValidationError(detail=tool_validation_message)

        tool_id = validated_uuid(tool_id, PromptStudioOutputManagerKeys.TOOL_ID)
        # Same column type, same failure: this one reaches
        # PromptStudioOutputManager.objects.filter(document_manager_id=...) in
        # the helper below. Required, not optional — absent it stays None and
        # compiles to `document_manager_id IS NULL`, which matches nothing and
        # renders every prompt as "", so the project looks empty while holding
        # real outputs. The only caller always sends it.
        if not document_manager_id:
            raise ValidationError(
                detail="'document_manager' is required and must be a valid UUID."
            )
        document_manager_id = validated_uuid(
            document_manager_id, PromptStudioOutputManagerKeys.DOCUMENT_MANAGER
        )
        organization = _required_organization(tool_id)

        # Fetch ToolStudioPrompt records based on tool_id.
        # Defence in depth, as above: OrgAwareManager already pins this model
        # to tool_id__organization, and a raw .objects query gets nothing from
        # the view layer.
        #
        # No exception handling below: for a valid UUID that matches no row, or
        # a tool in another organization, filter() returns empty rather than
        # raising. Empty is also the correct result for a tool that simply has
        # no prompts yet, the normal state of a newly created project — so that
        # case stays a 200 with an empty body.
        tool_studio_prompts = ToolStudioPrompt.objects.filter(
            tool_id=tool_id,
            tool_id__organization=organization,
        ).order_by("sequence_number")

        # Invoke helper method to frame and fetch default response.
        result: dict[str, Any] = OutputManagerHelper.fetch_default_output_response(
            tool_studio_prompts=tool_studio_prompts,
            document_manager_id=document_manager_id,
            use_default_profile=True,
        )

        return Response(result, status=status.HTTP_200_OK)
