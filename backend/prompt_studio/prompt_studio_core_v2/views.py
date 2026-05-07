import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import magic
from account_v2.custom_exceptions import DuplicateData
from api_v2.models import APIDeployment
from celery import signature
from celery.result import AsyncResult
from django.db import IntegrityError
from django.db.models import Count, OuterRef, QuerySet, Subquery
from django.http import HttpRequest, HttpResponse
from file_management.constants import FileInformationKey as FileKey
from file_management.exceptions import FileNotFound
from permissions.permission import IsOwner, IsOwnerOrSharedUserOrSharedToOrg
from pipeline_v2.models import Pipeline
from plugins import get_plugin
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tool_instance_v2.models import ToolInstance
from utils.file_storage.helpers.prompt_studio_file_helper import PromptStudioFileHelper
from utils.hubspot_notify import notify_hubspot_event
from utils.user_context import UserContext
from utils.user_session import UserSessionUtils
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

from backend.celery_service import app as celery_app
from prompt_studio.prompt_profile_manager_v2.constants import (
    ProfileManagerErrors,
    ProfileManagerKeys,
)
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_profile_manager_v2.serializers import ProfileManagerSerializer
from prompt_studio.prompt_studio_core_v2.constants import (
    DeploymentType,
    FileViewTypes,
    ToolStudioErrors,
    ToolStudioPromptKeys,
)
from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
    DocumentIndexingService,
)
from prompt_studio.prompt_studio_core_v2.exceptions import (
    DeploymentUsageCheckError,
    MaxProfilesReachedError,
    OperationNotSupported,
    ToolDeleteError,
)
from prompt_studio.prompt_studio_core_v2.migration_utils import SummarizeMigrationUtils
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_core_v2.retrieval_strategies import (
    get_retrieval_strategy_metadata,
)
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_document_manager_v2.prompt_studio_document_helper import (  # noqa: E501
    PromptStudioDocumentHelper,
)
from prompt_studio.prompt_studio_index_manager_v2.models import IndexManager
from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry
from prompt_studio.prompt_studio_registry_v2.prompt_studio_registry_helper import (
    PromptStudioRegistryHelper,
)
from prompt_studio.prompt_studio_registry_v2.serializers import (
    ExportToolRequestSerializer,
    PromptStudioRegistryInfoSerializer,
)
from prompt_studio.prompt_studio_v2.constants import ToolStudioPromptErrors
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from prompt_studio.prompt_studio_v2.serializers import ToolStudioPromptSerializer
from unstract.sdk1.utils.common import Utils as CommonUtils

from .models import CustomTool
from .serializers import (
    CustomToolListSerializer,
    CustomToolSerializer,
    FileInfoIdeSerializer,
    FileUploadIdeSerializer,
    PromptStudioIndexSerializer,
    SharedUserListSerializer,
    SyncPromptsSerializer,
)

logger = logging.getLogger(__name__)


class PromptStudioCoreView(viewsets.ModelViewSet):
    """Viewset to handle all Custom tool related operations."""

    versioning_class = URLPathVersioning

    serializer_class = CustomToolSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return CustomToolListSerializer
        return CustomToolSerializer

    def get_permissions(self) -> list[Any]:
        if self.action == "destroy":
            return [IsOwner()]

        return [IsOwnerOrSharedUserOrSharedToOrg()]

    def get_queryset(self) -> QuerySet | None:
        qs = CustomTool.objects.for_user(self.request.user)
        if self.action == "list":
            # Subquery avoids conflict with distinct("tool_id") from for_user()
            prompt_count_sq = (
                ToolStudioPrompt.objects.filter(tool_id=OuterRef("pk"))
                .order_by()
                .values("tool_id")
                .annotate(cnt=Count("prompt_id"))
                .values("cnt")
            )
            qs = qs.select_related("created_by").annotate(
                _prompt_count=Subquery(prompt_count_sq)
            )
        return qs

    def get_object(self):
        """Override get_object to trigger lazy migration when accessing tools."""
        instance = super().get_object()

        # Trigger lazy migration if needed (safe, with locking)
        SummarizeMigrationUtils.migrate_tool_to_adapter_based(instance)

        return instance

    def create(self, request: HttpRequest) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ToolStudioErrors.TOOL_NAME_EXISTS}, \
                    {ToolStudioErrors.DUPLICATE_API}"
            )
        PromptStudioHelper.create_default_profile_manager(
            request.user, serializer.data["tool_id"]
        )

        # Notify HubSpot if this is the first Prompt Studio project for the org
        # (count == 1 means the one we just created is the first)
        notify_hubspot_event(
            user=request.user,
            event_name="PROMPT_STUDIO_PROJECT_CREATE",
            is_first_for_org=CustomTool.objects.count() == 1,
            action_label="project creation",
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: CustomTool) -> None:
        organization_id = UserSessionUtils.get_organization_id(self.request)
        instance.delete(organization_id)

    def _check_tool_usage_in_workflows(self, instance: CustomTool) -> tuple[bool, set]:
        """Check if a tool is being used in any workflows.

        Args:
            instance: The CustomTool instance to check

        Returns:
            Tuple of (is_used: bool, dependent_workflows: set)
        """
        registry = getattr(instance, "prompt_studio_registries", None)
        if not registry:
            return False, set()

        dependent_wfs = set(
            ToolInstance.objects.filter(tool_id=registry.pk)
            .values_list("workflow_id", flat=True)
            .distinct()
        )
        return bool(dependent_wfs), dependent_wfs

    def _get_deployment_types(self, workflow_ids: set) -> set:
        """Get all deployment types where the tool is used.

        Args:
            workflow_ids: Set of workflow IDs to check

        Returns:
            Set of deployment type strings
        """
        deployment_types: set = set()

        # Check API Deployments (include inactive to prevent drift)
        if APIDeployment.objects.filter(workflow_id__in=workflow_ids).exists():
            deployment_types.add(DeploymentType.API_DEPLOYMENT)

        # Check Pipelines using mapping instead of if/elif
        pipeline_type_mapping = {
            Pipeline.PipelineType.ETL: DeploymentType.ETL_PIPELINE,
            Pipeline.PipelineType.TASK: DeploymentType.TASK_PIPELINE,
        }
        pipelines = (
            Pipeline.objects.filter(workflow_id__in=workflow_ids)
            .values_list("pipeline_type", flat=True)
            .distinct()
        )
        for pipeline_type in pipelines:
            if pipeline_type in pipeline_type_mapping:
                deployment_types.add(pipeline_type_mapping[pipeline_type])

        # Check for Manual Review
        if WorkflowEndpoint.objects.filter(
            workflow_id__in=workflow_ids,
            connection_type=WorkflowEndpoint.ConnectionType.MANUALREVIEW,
        ).exists():
            deployment_types.add(DeploymentType.HUMAN_QUALITY_REVIEW)

        return deployment_types

    def _format_deployment_types_message(self, deployment_types: set) -> str:
        """Format deployment types into human-readable message.

        Args:
            deployment_types: Set of deployment type strings

        Returns:
            Formatted message string or empty string if no types
        """
        if not deployment_types:
            return ""

        types_list = sorted(deployment_types)
        if len(types_list) == 1:
            types_text = types_list[0]
        elif len(types_list) == 2:
            types_text = f"{types_list[0]} or {types_list[1]}"
        else:
            types_text = ", ".join(types_list[:-1]) + f", or {types_list[-1]}"

        return (
            f"You have made changes to this Prompt Studio project. "
            f"This project is used in {types_text}. "
            f"Please export it for the changes to take effect in the deployment(s)."
        )

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        instance: CustomTool = self.get_object()
        # Checks if tool is exported
        is_used, dependent_wfs = self._check_tool_usage_in_workflows(instance)
        if is_used:
            logger.info(
                f"Cannot destroy custom tool {instance.tool_id},"
                f" depended by workflows {dependent_wfs}"
            )
            raise ToolDeleteError(
                "Failed to delete Prompt Studio project; it's used in other workflows."
                "Delete its usages first."
            )
        return super().destroy(request, *args, **kwargs)

    def partial_update(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        # Store current shared users before update for email notifications
        custom_tool = self.get_object()
        current_shared_users = set(custom_tool.shared_users.all())

        # Perform the update
        response = super().partial_update(request, *args, **kwargs)

        # Send email notifications to newly shared users
        if response.status_code == 200 and "shared_users" in request.data:
            from plugins import get_plugin

            notification_plugin = get_plugin("notification")
            if notification_plugin:
                from plugins.notification.constants import ResourceType

                # Refresh the object to get updated shared_users
                custom_tool.refresh_from_db()
                updated_shared_users = set(custom_tool.shared_users.all())

                # Find newly added users (not previously shared)
                newly_shared_users = updated_shared_users - current_shared_users

                if newly_shared_users:
                    service_class = notification_plugin["service_class"]
                    notification_service = service_class()
                    try:
                        notification_service.send_sharing_notification(
                            resource_type=ResourceType.TEXT_EXTRACTOR.value,
                            resource_name=custom_tool.tool_name,
                            resource_id=str(custom_tool.tool_id),
                            shared_by=request.user,
                            shared_to=list(newly_shared_users),
                            resource_instance=custom_tool,
                        )
                    except Exception as e:
                        # Log error but don't fail the request
                        logger.exception(
                            f"Failed to send sharing notification for "
                            f"custom tool {custom_tool.tool_id}: {str(e)}"
                        )

        return response

    @action(detail=True, methods=["get"])
    def get_select_choices(self, request: HttpRequest) -> Response:
        """Method to return all static dropdown field values.

        The field values are retrieved from `./static/select_choices.json`.

        Returns:
            Response: Reponse of dropdown dict
        """
        try:
            select_choices: dict[str, Any] = PromptStudioHelper.get_select_fields()
            return Response(select_choices, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("Error occurred while fetching select fields: %s", e)
            return Response(select_choices, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def get_retrieval_strategies(self, request: HttpRequest, pk: Any = None) -> Response:
        """Method to return all retrieval strategy metadata.

        Returns detailed information about each retrieval strategy including
        descriptions, use cases, performance impacts, and technical details.

        Args:
            request (HttpRequest): The HTTP request
            pk (Any): Primary key of the tool (not used in this method)

        Returns:
            Response: Response containing retrieval strategy metadata
        """
        try:
            strategies = get_retrieval_strategy_metadata()
            return Response(strategies, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("Error occurred while fetching retrieval strategies: %s", e)
            return Response(
                {"error": "Failed to fetch retrieval strategies"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def list_profiles(self, request: HttpRequest, pk: Any = None) -> Response:
        prompt_tool = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        profile_manager_instances = ProfileManager.objects.filter(
            prompt_studio_tool=prompt_tool
        )

        serialized_instances = ProfileManagerSerializer(
            profile_manager_instances, many=True
        ).data

        return Response(serialized_instances)

    @action(detail=True, methods=["patch"])
    def make_profile_default(self, request: HttpRequest, pk: Any = None) -> Response:
        prompt_tool = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        ProfileManager.objects.filter(prompt_studio_tool=prompt_tool).update(
            is_default=False
        )

        profile_manager = ProfileManager.objects.get(pk=request.data["default_profile"])
        profile_manager.is_default = True
        profile_manager.save()

        return Response(
            status=status.HTTP_200_OK,
            data={"default_profile": profile_manager.profile_id},
        )

    @action(detail=True, methods=["post"])
    def index_document(self, request: HttpRequest, pk: Any = None) -> Response:
        """API Entry point method to index input file.

        Builds the full execution payload (ORM work), then fires a
        single executor task with Celery link/link_error callbacks.
        The backend worker slot is freed immediately.

        Args:
            request (HttpRequest)

        Raises:
            IndexingError
            ValidationError

        Returns:
            Response
        """
        tool = self.get_object()
        serializer = PromptStudioIndexSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        file_name: str = document.document_name
        run_id = CommonUtils.generate_uuid()

        context, cb_kwargs = PromptStudioHelper.build_index_payload(
            tool_id=str(tool.tool_id),
            file_name=file_name,
            org_id=UserSessionUtils.get_organization_id(request),
            user_id=tool.created_by.user_id,
            document_id=document_id,
            run_id=run_id,
        )

        dispatcher = PromptStudioHelper._get_dispatcher()

        # Pre-generate task ID so callbacks can reference it
        executor_task_id = str(uuid.uuid4())
        cb_kwargs["executor_task_id"] = executor_task_id

        # Mark as indexing in progress — placed here so the except block
        # below can clean up the lock if dispatch_with_callback fails.
        DocumentIndexingService.set_document_indexing(
            org_id=cb_kwargs["org_id"],
            user_id=cb_kwargs["user_id"],
            doc_id_key=cb_kwargs["doc_id_key"],
        )

        try:
            task = dispatcher.dispatch_with_callback(
                context,
                on_success=signature(
                    "ide_index_complete",
                    kwargs={"callback_kwargs": cb_kwargs},
                    queue="ide_callback",
                ),
                on_error=signature(
                    "ide_index_error",
                    kwargs={"callback_kwargs": cb_kwargs},
                    queue="ide_callback",
                ),
                task_id=executor_task_id,
            )
        except Exception:
            DocumentIndexingService.remove_document_indexing(
                org_id=cb_kwargs["org_id"],
                user_id=cb_kwargs["user_id"],
                doc_id_key=cb_kwargs["doc_id_key"],
            )
            raise
        return Response(
            {"task_id": task.id, "run_id": run_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def fetch_response(self, request: HttpRequest, pk: Any = None) -> Response:
        """API Entry point method to fetch response to prompt.

        Builds the full execution payload (ORM work), then fires a
        single executor task with Celery link/link_error callbacks.

        Args:
            request (HttpRequest)

        Returns:
            Response
        """
        custom_tool = self.get_object()
        document_id: str = request.data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        prompt_id: str = request.data.get(ToolStudioPromptKeys.ID)
        run_id: str = request.data.get(ToolStudioPromptKeys.RUN_ID)
        profile_manager_id: str = request.data.get(
            ToolStudioPromptKeys.PROFILE_MANAGER_ID
        )
        if not run_id:
            run_id = CommonUtils.generate_uuid()

        org_id = UserSessionUtils.get_organization_id(request)
        user_id = custom_tool.created_by.user_id

        # Resolve prompt — guard against missing / stale prompt_id
        if not prompt_id:
            return Response(
                {"error": "prompt id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            prompt = ToolStudioPrompt.objects.get(pk=prompt_id)
        except ToolStudioPrompt.DoesNotExist:
            return Response(
                {"error": f"Prompt {prompt_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Build file path
        doc_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
            org_id,
            is_create=False,
            user_id=user_id,
            tool_id=str(custom_tool.tool_id),
        )
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        doc_path = str(Path(doc_path) / document.document_name)

        # Agentic table prompts have a separate executor worker. Build the
        # payload via the cloud payload_modifier plugin and dispatch directly
        # so the legacy answer_prompt path is bypassed.
        if prompt.enforce_type == ToolStudioPromptKeys.AGENTIC_TABLE:
            payload_modifier_plugin = get_plugin("payload_modifier")
            if not payload_modifier_plugin:
                raise OperationNotSupported()
            modifier = payload_modifier_plugin["service_class"]()
            context, cb_kwargs = modifier.build_agentic_table_payload(
                tool=custom_tool,
                prompt=prompt,
                doc_path=doc_path,
                doc_name=document.document_name,
                org_id=org_id,
                user_id=user_id,
                document_id=document_id,
                run_id=run_id,
                profile_manager_id=profile_manager_id,
            )

            from prompt_studio.prompt_studio_output_manager_v2.models import (
                PromptStudioOutputManager,
            )

            cb_kwargs["hubspot_user_id"] = request.user.pk
            cb_kwargs[
                "is_first_prompt_run"
            ] = not PromptStudioOutputManager.objects.filter(
                tool_id__in=CustomTool.objects.values_list("tool_id", flat=True)
            ).exists()

            dispatcher = PromptStudioHelper._get_dispatcher()
            executor_task_id = str(uuid.uuid4())
            cb_kwargs["executor_task_id"] = executor_task_id
            cb_kwargs["dispatch_time"] = time.time()

            task = dispatcher.dispatch_with_callback(
                context,
                on_success=signature(
                    "ide_prompt_complete",
                    kwargs={"callback_kwargs": cb_kwargs},
                    queue="ide_callback",
                ),
                on_error=signature(
                    "ide_prompt_error",
                    kwargs={"callback_kwargs": cb_kwargs},
                    queue="ide_callback",
                ),
                task_id=executor_task_id,
            )
            return Response(
                {"task_id": task.id, "run_id": run_id, "status": "accepted"},
                status=status.HTTP_202_ACCEPTED,
            )

        context, cb_kwargs = PromptStudioHelper.build_fetch_response_payload(
            tool=custom_tool,
            doc_path=doc_path,
            doc_name=document.document_name,
            prompt=prompt,
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            run_id=run_id,
            profile_manager_id=profile_manager_id,
        )

        # If document is being indexed, return pending status
        if context is None:
            return Response(cb_kwargs, status=status.HTTP_202_ACCEPTED)

        # Capture HubSpot first-run state before dispatch so the callback
        # can fire the PROMPT_RUN analytics event on success.
        from prompt_studio.prompt_studio_output_manager_v2.models import (
            PromptStudioOutputManager,
        )

        cb_kwargs["hubspot_user_id"] = request.user.pk
        cb_kwargs["is_first_prompt_run"] = not PromptStudioOutputManager.objects.filter(
            tool_id__in=CustomTool.objects.values_list("tool_id", flat=True)
        ).exists()

        dispatcher = PromptStudioHelper._get_dispatcher()

        executor_task_id = str(uuid.uuid4())
        cb_kwargs["executor_task_id"] = executor_task_id
        cb_kwargs["dispatch_time"] = time.time()

        task = dispatcher.dispatch_with_callback(
            context,
            on_success=signature(
                "ide_prompt_complete",
                kwargs={"callback_kwargs": cb_kwargs},
                queue="ide_callback",
            ),
            on_error=signature(
                "ide_prompt_error",
                kwargs={"callback_kwargs": cb_kwargs},
                queue="ide_callback",
            ),
            task_id=executor_task_id,
        )
        return Response(
            {"task_id": task.id, "run_id": run_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def bulk_fetch_response(self, request: HttpRequest, pk: Any = None) -> Response:
        """Bulk fetch_response: accept multiple prompt IDs, extract and index
        once, then dispatch a single executor task for all prompts.

        Prevents the "Document being indexed" race when the frontend fires
        N individual fetch_response requests concurrently on an unindexed
        document.
        """
        custom_tool = self.get_object()
        prompt_ids = request.data.get("prompt_ids", [])
        if not prompt_ids:
            return Response(
                {"error": "prompt_ids is required and must be non-empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        document_id: str = request.data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        run_id: str = request.data.get(ToolStudioPromptKeys.RUN_ID)
        profile_manager_id: str = request.data.get(
            ToolStudioPromptKeys.PROFILE_MANAGER_ID
        )
        if not run_id:
            run_id = CommonUtils.generate_uuid()

        org_id = UserSessionUtils.get_organization_id(request)
        user_id = custom_tool.created_by.user_id

        prompts = list(
            ToolStudioPrompt.objects.filter(prompt_id__in=prompt_ids).order_by(
                "sequence_number"
            )
        )
        if not prompts:
            return Response(
                {"error": "No matching prompts found for the provided prompt_ids."},
                status=status.HTTP_404_NOT_FOUND,
            )

        doc_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
            org_id,
            is_create=False,
            user_id=user_id,
            tool_id=str(custom_tool.tool_id),
        )
        if not document_id:
            return Response(
                {"error": "document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        except DocumentManager.DoesNotExist:
            return Response(
                {"error": f"Document {document_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        doc_path = str(Path(doc_path) / document.document_name)

        context, cb_kwargs = PromptStudioHelper.build_bulk_fetch_response_payload(
            tool=custom_tool,
            doc_path=doc_path,
            doc_name=document.document_name,
            prompts=prompts,
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            run_id=run_id,
            profile_manager_id=profile_manager_id,
        )

        if context is None:
            return Response(cb_kwargs, status=status.HTTP_202_ACCEPTED)

        # Capture HubSpot first-run state before dispatch so the callback
        # can fire the PROMPT_RUN analytics event on success.
        from prompt_studio.prompt_studio_output_manager_v2.models import (
            PromptStudioOutputManager,
        )

        cb_kwargs["hubspot_user_id"] = request.user.pk
        cb_kwargs["is_first_prompt_run"] = not PromptStudioOutputManager.objects.filter(
            tool_id__in=CustomTool.objects.values_list("tool_id", flat=True)
        ).exists()

        dispatcher = PromptStudioHelper._get_dispatcher()

        executor_task_id = str(uuid.uuid4())
        cb_kwargs["executor_task_id"] = executor_task_id
        cb_kwargs["dispatch_time"] = time.time()

        task = dispatcher.dispatch_with_callback(
            context,
            on_success=signature(
                "ide_prompt_complete",
                kwargs={"callback_kwargs": cb_kwargs},
                queue="ide_callback",
            ),
            on_error=signature(
                "ide_prompt_error",
                kwargs={"callback_kwargs": cb_kwargs},
                queue="ide_callback",
            ),
            task_id=executor_task_id,
        )
        return Response(
            {"task_id": task.id, "run_id": run_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def single_pass_extraction(self, request: HttpRequest, pk: uuid) -> Response:
        """API Entry point method for single pass extraction.

        Builds the full execution payload (ORM work), then fires a
        single executor task with Celery link/link_error callbacks.

        Args:
            request (HttpRequest)
            pk: Primary key of the CustomTool

        Returns:
            Response
        """
        custom_tool = self.get_object()
        document_id: str = request.data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        run_id: str = request.data.get(ToolStudioPromptKeys.RUN_ID)
        if not run_id:
            run_id = CommonUtils.generate_uuid()

        org_id = UserSessionUtils.get_organization_id(request)
        user_id = custom_tool.created_by.user_id

        # Build file path
        doc_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
            org_id,
            is_create=False,
            user_id=user_id,
            tool_id=str(custom_tool.tool_id),
        )
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        doc_path = str(Path(doc_path) / document.document_name)

        # Fetch prompts eligible for single-pass extraction.
        # Mirrors the filtering in _execute_prompts_in_single_pass:
        # only active, non-NOTES, non-TABLE/RECORD/AGENTIC_TABLE prompts.
        prompts = list(
            ToolStudioPrompt.objects.filter(tool_id=custom_tool.tool_id).order_by(
                "sequence_number"
            )
        )
        prompts = [
            p
            for p in prompts
            if p.prompt_type != ToolStudioPromptKeys.NOTES
            and p.active
            and p.enforce_type != ToolStudioPromptKeys.TABLE
            and p.enforce_type != ToolStudioPromptKeys.RECORD
            and p.enforce_type != ToolStudioPromptKeys.AGENTIC_TABLE
        ]
        if not prompts:
            return Response(
                {"error": "No active prompts found for single pass extraction."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        context, cb_kwargs = PromptStudioHelper.build_single_pass_payload(
            tool=custom_tool,
            doc_path=doc_path,
            doc_name=document.document_name,
            prompts=prompts,
            org_id=org_id,
            user_id=user_id,
            document_id=document_id,
            run_id=run_id,
        )

        dispatcher = PromptStudioHelper._get_dispatcher()

        executor_task_id = str(uuid.uuid4())
        cb_kwargs["executor_task_id"] = executor_task_id
        cb_kwargs["dispatch_time"] = time.time()

        task = dispatcher.dispatch_with_callback(
            context,
            on_success=signature(
                "ide_prompt_complete",
                kwargs={"callback_kwargs": cb_kwargs},
                queue="ide_callback",
            ),
            on_error=signature(
                "ide_prompt_error",
                kwargs={"callback_kwargs": cb_kwargs},
                queue="ide_callback",
            ),
            task_id=executor_task_id,
        )
        return Response(
            {"task_id": task.id, "run_id": run_id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def task_status(
        self, request: HttpRequest, pk: Any = None, task_id: str = None
    ) -> Response:
        """Poll the status of an async Prompt Studio task.

        Task IDs now point to executor worker tasks dispatched via the
        worker-v2 Celery app.  Both apps share the same PostgreSQL
        result backend, so we use the worker app to look up results.

        Args:
            request (HttpRequest)
            pk: Primary key of the CustomTool (for permission check)
            task_id: Celery task ID returned by the 202 response

        Returns:
            Response with {task_id, status} and optionally result or error
        """
        # Verify the user has access to this tool (triggers permission check)
        self.get_object()

        result = AsyncResult(task_id, app=celery_app)
        if not result.ready():
            return Response({"task_id": task_id, "status": "processing"})
        if result.successful():
            return Response({"task_id": task_id, "status": "completed"})
        return Response(
            {"task_id": task_id, "status": "failed", "error": str(result.result)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:
        custom_tool = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        serialized_instances = SharedUserListSerializer(custom_tool).data

        return Response(serialized_instances)

    @action(detail=True, methods=["post"])
    def create_prompt(self, request: HttpRequest, pk: Any = None) -> Response:
        context = super().get_serializer_context()
        serializer = ToolStudioPromptSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        try:
            # serializer.save()
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ToolStudioPromptErrors.PROMPT_NAME_EXISTS}, \
                    {ToolStudioPromptErrors.DUPLICATE_API}"
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # TODO: Move to prompt_profile_manager app and move validation to serializer
    @action(detail=True, methods=["post"])
    def create_profile_manager(self, request: HttpRequest, pk: Any = None) -> Response:
        context = super().get_serializer_context()
        serializer = ProfileManagerSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        # Check for the maximum number of profiles constraint
        prompt_studio_tool = serializer.validated_data[
            ProfileManagerKeys.PROMPT_STUDIO_TOOL
        ]
        profile_count = ProfileManager.objects.filter(
            prompt_studio_tool=prompt_studio_tool
        ).count()

        if profile_count >= ProfileManagerKeys.MAX_PROFILE_COUNT:
            raise MaxProfilesReachedError()
        try:
            self.perform_create(serializer)
            # Check if this is the first profile and make it default for all prompts
            if profile_count == 0:
                profile_manager = serializer.instance  # Newly created profile manager
                ToolStudioPrompt.objects.filter(tool_id=prompt_studio_tool).update(
                    profile_manager=profile_manager
                )

        except IntegrityError:
            raise DuplicateData(
                f"{ProfileManagerErrors.PROFILE_NAME_EXISTS}, \
                    {ProfileManagerErrors.DUPLICATE_API}"
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def fetch_contents_ide(self, request: HttpRequest, pk: Any = None) -> Response:
        custom_tool = self.get_object()
        serializer = FileInfoIdeSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get("document_id")
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        file_name: str = document.document_name
        view_type: str = serializer.validated_data.get("view_type")
        file_converter_plugin = get_plugin("file_converter")

        allowed_content_types = FileKey.FILE_UPLOAD_ALLOWED_MIME
        if file_converter_plugin:
            file_converter_service = file_converter_plugin["service_class"]()
            allowed_content_types = (
                file_converter_service.get_extented_file_information_key()
            )
        filename_without_extension = file_name.rsplit(".", 1)[0]
        if view_type == FileViewTypes.EXTRACT:
            file_name = (
                f"{FileViewTypes.EXTRACT.lower()}/{filename_without_extension}.txt"
            )
        if view_type == FileViewTypes.SUMMARIZE:
            file_name = (
                f"{FileViewTypes.SUMMARIZE.lower()}/{filename_without_extension}.txt"
            )

        # For ORIGINAL view, check if a converted PDF exists for preview
        if (
            view_type != FileViewTypes.EXTRACT
            and view_type != FileViewTypes.SUMMARIZE
            and file_converter_plugin
        ):
            converted_name = f"converted/{filename_without_extension}.pdf"
            try:
                contents = PromptStudioFileHelper.fetch_file_contents(
                    file_name=converted_name,
                    org_id=UserSessionUtils.get_organization_id(request),
                    user_id=custom_tool.created_by.user_id,
                    tool_id=str(custom_tool.tool_id),
                    allowed_content_types=allowed_content_types,
                )
                return Response(contents, status=status.HTTP_200_OK)
            except (FileNotFoundError, FileNotFound):
                pass  # No converted file — fall through to return original
            except Exception:
                logger.exception("Error fetching converted file: %s", converted_name)

        try:
            contents = PromptStudioFileHelper.fetch_file_contents(
                file_name=file_name,
                org_id=UserSessionUtils.get_organization_id(request),
                user_id=custom_tool.created_by.user_id,
                tool_id=str(custom_tool.tool_id),
                allowed_content_types=allowed_content_types,
            )
        except FileNotFoundError:
            raise FileNotFound()
        return Response(contents, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def upload_for_ide(self, request: HttpRequest, pk: Any = None) -> Response:
        custom_tool = self.get_object()
        serializer = FileUploadIdeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_files: Any = serializer.validated_data.get("file")
        file_converter_plugin = get_plugin("file_converter")

        # Check document count before upload for HubSpot notification
        # Filter through tool FK to scope by organization (DocumentManager
        # lacks DefaultOrganizationManagerMixin)
        doc_count_before = DocumentManager.objects.filter(
            tool__in=CustomTool.objects.all()
        ).count()

        documents = []
        for uploaded_file in uploaded_files:
            # Store file
            file_name = uploaded_file.name
            file_data = uploaded_file
            # Detect MIME from file content (not browser-supplied header)
            file_type = magic.from_buffer(uploaded_file.read(2048), mime=True)
            uploaded_file.seek(0)

            if file_converter_plugin and file_type != "application/pdf":
                file_converter_service = file_converter_plugin["service_class"]()
                if file_converter_service.should_convert_to_pdf(file_type):
                    # Convert and store in converted/ subdir for preview
                    converted_data, converted_name = file_converter_service.process_file(
                        uploaded_file, file_name
                    )
                    PromptStudioFileHelper.upload_converted_for_ide(
                        org_id=UserSessionUtils.get_organization_id(request),
                        user_id=custom_tool.created_by.user_id,
                        tool_id=str(custom_tool.tool_id),
                        file_name=converted_name,
                        file_data=converted_data,
                    )
                    # Reset uploaded_file for storing original in main dir
                    uploaded_file.seek(0)
                    file_data = uploaded_file
                # else: CSV/TXT/Excel — file_data stays as original, no conversion

            logger.info("Uploading file: %s", file_name) if file_name else logger.info(
                "Uploading file"
            )

            # Store original file in main dir (always the original)
            PromptStudioFileHelper.upload_for_ide(
                org_id=UserSessionUtils.get_organization_id(request),
                user_id=custom_tool.created_by.user_id,
                tool_id=str(custom_tool.tool_id),
                file_name=file_name,
                file_data=file_data,
            )

            # Create a record in the db for the file (document_name = original filename)
            document = PromptStudioDocumentHelper.create(
                tool_id=str(custom_tool.tool_id), document_name=file_name
            )
            # Create a dictionary to store document data
            doc = {
                "document_id": document.document_id,
                "document_name": document.document_name,
                "tool": document.tool.tool_id,
            }
            documents.append(doc)

        # Notify HubSpot about first document upload
        notify_hubspot_event(
            user=request.user,
            event_name="DOCUMENT_UPLOAD",
            is_first_for_org=doc_count_before == 0,
            action_label="document upload",
        )

        return Response({"data": documents})

    @action(detail=True, methods=["delete"])
    def delete_for_ide(self, request: HttpRequest, pk: uuid) -> Response:
        custom_tool = self.get_object()
        serializer = FileInfoIdeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get(ToolStudioPromptKeys.DOCUMENT_ID)
        org_id = UserSessionUtils.get_organization_id(request)
        user_id = custom_tool.created_by.user_id
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)

        try:
            # Delete indexed flags in redis
            index_managers = IndexManager.objects.filter(document_manager=document_id)
            for index_manager in index_managers:
                raw_index_id = index_manager.raw_index_id
                DocumentIndexingService.remove_document_indexing(
                    org_id=org_id, user_id=user_id, doc_id_key=raw_index_id
                )
            # Delete the document record
            document.delete()
            # Delete the files
            file_name: str = document.document_name
            PromptStudioFileHelper.delete_for_ide(
                org_id=org_id,
                user_id=user_id,
                tool_id=str(custom_tool.tool_id),
                file_name=file_name,
            )
            return Response(
                {"data": "File deleted succesfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.error("Exception thrown from file deletion, error: %s", exc)
            return Response(
                {"data": "File deletion failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def export_tool(self, request: Request, pk: Any = None) -> Response:
        """API Endpoint for exporting required jsons for the custom tool."""
        custom_tool = self.get_object()
        serializer = ExportToolRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_shared_with_org: bool = serializer.validated_data.get("is_shared_with_org")
        user_ids = set(serializer.validated_data.get("user_id") or [])
        force_export = serializer.validated_data.get("force_export")

        # Check registry count before export for HubSpot notification
        registry_count_before = PromptStudioRegistry.objects.count()

        PromptStudioRegistryHelper.update_or_create_psr_tool(
            custom_tool=custom_tool,
            shared_with_org=is_shared_with_org,
            user_ids=user_ids,
            force_export=force_export,
        )

        # Notify HubSpot about first tool export
        notify_hubspot_event(
            user=request.user,
            event_name="TOOL_EXPORT",
            is_first_for_org=registry_count_before == 0,
            action_label="tool export",
        )

        return Response(
            {"message": "Custom tool exported sucessfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def export_tool_info(self, request: Request, pk: Any = None) -> Response:
        custom_tool = self.get_object()
        serialized_instances = None
        if hasattr(custom_tool, "prompt_studio_registries"):
            serialized_instances = PromptStudioRegistryInfoSerializer(
                custom_tool.prompt_studio_registries
            ).data

            return Response(serialized_instances)
        else:
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def export_project(self, request: Request, pk: Any = None) -> HttpResponse:
        """API Endpoint for exporting project settings as downloadable JSON."""
        custom_tool = self.get_object()

        try:
            # Get the export data using our helper method
            export_data = PromptStudioHelper.export_project_settings(custom_tool)

            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{custom_tool.tool_name}_{timestamp}.json"

            # Create HTTP response with JSON file
            response = HttpResponse(
                json.dumps(export_data, indent=2), content_type="application/json"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            return response

        except Exception as exc:
            logger.error("Error exporting project: %s", exc)
            return Response(
                {"error": "Failed to export project"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"])
    def import_project(self, request: Request) -> Response:
        """API Endpoint for importing project settings from JSON file."""
        try:
            import_data, selected_adapters = PromptStudioHelper.validate_import_file(
                request
            )

            organization = UserContext.get_organization()
            if not organization:
                return Response(
                    {"error": "Unable to determine organization context"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tool_name = PromptStudioHelper.generate_unique_tool_name(
                import_data["tool_metadata"]["tool_name"], organization
            )

            new_tool = PromptStudioHelper.create_tool_from_import_data(
                import_data, tool_name, organization, request.user
            )

            try:
                PromptStudioHelper.create_profile_manager(
                    import_data, selected_adapters, new_tool, request.user
                )
            except ValueError as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.error("Error creating profile manager: %s", e)
                return Response(
                    {"error": "Failed to create profile manager"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            PromptStudioHelper.import_prompts(
                import_data["prompts"], new_tool, request.user
            )

            needs_adapter_config, warning_message = (
                PromptStudioHelper.validate_adapter_configuration(
                    selected_adapters, new_tool
                )
            )

            response_data = {
                "message": f"Project imported successfully as '{tool_name}'",
                "tool_id": str(new_tool.tool_id),
                "needs_adapter_config": needs_adapter_config,
            }

            if warning_message:
                response_data["warning"] = warning_message

            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.error("Error importing project: %s", exc)
            return Response(
                {"error": "Failed to import project"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def sync_prompts(self, request: Request, pk: Any = None) -> Response:
        """Sync prompts from export JSON into an existing project.

        Rip-and-replace: deletes all existing prompts and creates new ones
        from the export data. Tool settings are also updated.
        Profiles and adapters are left untouched.

        Request body:
            data (dict): The export JSON containing "prompts" key
            create_copy (bool): If true, clone the project before syncing
        """
        tool = self.get_object()

        serializer = SyncPromptsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        import_data = serializer.validated_data["data"]
        create_copy = serializer.validated_data["create_copy"]

        response_data = {}

        # Create a backup copy if requested
        if create_copy:
            organization = UserContext.get_organization()
            export_data = PromptStudioHelper.export_project_settings(tool)
            backup_name = PromptStudioHelper.generate_unique_tool_name(
                f"{tool.tool_name} (backup)", organization
            )
            backup_tool = PromptStudioHelper.create_tool_from_import_data(
                export_data, backup_name, organization, request.user
            )
            # Copy profiles from original to backup
            for profile in ProfileManager.objects.filter(prompt_studio_tool=tool):
                profile.pk = None
                profile.prompt_studio_tool = backup_tool
                profile.save()

            PromptStudioHelper.import_prompts(
                export_data["prompts"], backup_tool, request.user
            )
            response_data["backup_tool_id"] = str(backup_tool.tool_id)
            response_data["backup_tool_name"] = backup_name

        # Sync prompts into the target tool
        sync_result = PromptStudioHelper.sync_prompts(tool, import_data, request.user)
        response_data.update(sync_result)
        response_data["message"] = (
            f"Synced {sync_result['prompts_created']} prompts into '{tool.tool_name}'"
        )

        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def check_deployment_usage(self, request: Request, pk: Any = None) -> Response:
        """Check if the Prompt Studio project is used in any deployments.

        This endpoint checks if the exported tool from this project is being used in:
        - API Deployments
        - ETL Pipelines
        - Task Pipelines
        - Manual Review (Human Quality Review)

        Returns:
            Response: Contains is_used flag and deployment types where it's used
        """
        try:
            instance: CustomTool = self.get_object()
            is_used, workflow_ids = self._check_tool_usage_in_workflows(instance)

            deployment_info: dict = {
                "is_used": is_used,
                "deployment_types": [],
                "message": "",
            }

            if is_used and workflow_ids:
                deployment_types = self._get_deployment_types(workflow_ids)
                deployment_info["deployment_types"] = list(deployment_types)
                deployment_info["message"] = self._format_deployment_types_message(
                    deployment_types
                )

            return Response(deployment_info, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Error checking deployment usage for tool %s: %s", pk, e)
            raise DeploymentUsageCheckError(
                detail=f"Failed to check deployment usage: {str(e)}"
            )
