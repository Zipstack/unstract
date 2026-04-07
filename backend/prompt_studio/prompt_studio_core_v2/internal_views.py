"""Internal API views for Prompt Studio IDE callbacks.

These endpoints are called by the ide_callback worker (via InternalAPIClient)
to perform Django ORM operations that were previously done directly in the
backend callback tasks. Moving these behind HTTP keeps the worker image
free of Django dependencies.

Security note: @csrf_exempt is safe here because these endpoints are
internal-only (called by backend workers via service-to-service HTTP,
not by browsers). They are bound to the internal URL namespace and are
not exposed to end users.
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status

logger = logging.getLogger(__name__)

_ERR_INVALID_JSON = "Invalid JSON"


def _parse_json_body(request):
    """Parse JSON from request body, returning (data, None) or (None, JsonResponse)."""
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse(
            {"success": False, "error": _ERR_INVALID_JSON},
            status=status.HTTP_400_BAD_REQUEST,
        )


@csrf_exempt
@require_http_methods(["POST"])
def prompt_output(request):
    """Persist prompt execution output via OutputManagerHelper.

    Expected JSON payload:
    {
        "run_id": str,
        "prompt_ids": [str, ...],
        "outputs": dict,
        "document_id": str,
        "is_single_pass_extract": bool,
        "profile_manager_id": str | null,
        "metadata": dict
    }
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    run_id = data.get("run_id", "")
    prompt_ids = data.get("prompt_ids", [])
    outputs = data.get("outputs", {})
    document_id = data.get("document_id", "")
    is_single_pass = data.get("is_single_pass_extract", False)
    profile_manager_id = data.get("profile_manager_id")
    metadata = data.get("metadata", {})

    if not prompt_ids or not document_id:
        return JsonResponse(
            {"success": False, "error": "prompt_ids and document_id are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from prompt_studio.prompt_studio_output_manager_v2.output_manager_helper import (
            OutputManagerHelper,
        )
        from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

        prompts = list(
            ToolStudioPrompt.objects.filter(prompt_id__in=prompt_ids).order_by(
                "sequence_number"
            )
        )

        response = OutputManagerHelper.handle_prompt_output_update(
            run_id=run_id,
            prompts=prompts,
            outputs=outputs,
            document_id=document_id,
            is_single_pass_extract=is_single_pass,
            profile_manager_id=profile_manager_id,
            metadata=metadata,
        )
        return JsonResponse({"success": True, "data": response})

    except Exception as e:
        logger.exception("prompt_output internal API failed")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@csrf_exempt
@require_http_methods(["POST"])
def index_update(request):
    """Update IndexManager after successful indexing.

    Expected JSON payload:
    {
        "document_id": str,
        "profile_manager_id": str,
        "doc_id": str,
        "is_summary": bool (optional, default false)
    }
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    document_id = data.get("document_id", "")
    profile_manager_id = data.get("profile_manager_id", "")
    doc_id = data.get("doc_id", "")
    is_summary = data.get("is_summary", False)

    if not document_id or not profile_manager_id or not doc_id:
        return JsonResponse(
            {
                "success": False,
                "error": "document_id, profile_manager_id, and doc_id are required",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
        from prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper import (
            PromptStudioIndexHelper,
        )

        profile_manager = ProfileManager.objects.get(pk=profile_manager_id)
        PromptStudioIndexHelper.handle_index_manager(
            document_id=document_id,
            profile_manager=profile_manager,
            doc_id=doc_id,
            is_summary=is_summary,
        )
        return JsonResponse({"success": True})

    except Exception as e:
        logger.exception("index_update internal API failed")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@csrf_exempt
@require_http_methods(["POST"])
def indexing_status(request):
    """Update document indexing cache status (mark indexed or remove).

    Expected JSON payload:
    {
        "action": "mark_indexed" | "remove",
        "org_id": str,
        "user_id": str,
        "doc_id_key": str,
        "doc_id": str (required when action == "mark_indexed")
    }
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    action = data.get("action", "")
    org_id = data.get("org_id", "")
    user_id = data.get("user_id", "")
    doc_id_key = data.get("doc_id_key", "")

    if not action or not org_id or not user_id or not doc_id_key:
        return JsonResponse(
            {
                "success": False,
                "error": "action, org_id, user_id, doc_id_key are required",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
            DocumentIndexingService,
        )

        if action == "mark_indexed":
            doc_id = data.get("doc_id", "")
            if not doc_id:
                return JsonResponse(
                    {"success": False, "error": "doc_id required for mark_indexed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            DocumentIndexingService.mark_document_indexed(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key, doc_id=doc_id
            )
        elif action == "remove":
            DocumentIndexingService.remove_document_indexing(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
            )
        else:
            return JsonResponse(
                {"success": False, "error": f"Unknown action: {action}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return JsonResponse({"success": True})

    except Exception as e:
        logger.exception("indexing_status internal API failed")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@require_http_methods(["GET"])
def profile_detail(request, profile_id):
    """Return profile manager details needed by the worker for summary indexing.

    Returns vector_store, embedding_model, x2text adapter IDs and chunk_overlap.
    """
    try:
        from prompt_studio.prompt_profile_manager_v2.models import ProfileManager

        profile = ProfileManager.objects.get(pk=profile_id)
        return JsonResponse(
            {
                "success": True,
                "data": {
                    "profile_id": str(profile.profile_id),
                    "vector_store_id": str(profile.vector_store_id),
                    "embedding_model_id": str(profile.embedding_model_id),
                    "x2text_id": str(profile.x2text_id),
                    "chunk_overlap": profile.chunk_overlap,
                    "chunk_size": profile.chunk_size,
                },
            }
        )

    except Exception as e:
        logger.exception("profile_detail internal API failed")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@csrf_exempt
@require_http_methods(["POST"])
def hubspot_notify(request):
    """Fire a HubSpot event for a given user.

    Expected JSON payload:
    {
        "user_id": str,
        "event_name": str,
        "is_first_for_org": bool,
        "action_label": str
    }
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    user_id = data.get("user_id", "")
    event_name = data.get("event_name", "")
    is_first_for_org = data.get("is_first_for_org", False)
    action_label = data.get("action_label", "")

    if not user_id or not event_name:
        return JsonResponse(
            {"success": False, "error": "user_id and event_name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from django.contrib.auth import get_user_model
        from utils.hubspot_notify import notify_hubspot_event

        user_model = get_user_model()
        user = user_model.objects.get(pk=user_id)
        notify_hubspot_event(
            user=user,
            event_name=event_name,
            is_first_for_org=is_first_for_org,
            action_label=action_label,
        )
        return JsonResponse({"success": True})

    except Exception as e:
        logger.warning("hubspot_notify internal API failed: %s", e)
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@csrf_exempt
@require_http_methods(["POST"])
def summary_index_key(request):
    """Compute summary doc_id hash server-side.

    This requires PromptIdeBaseTool (Django ORM + SDK1) which is only
    available on the backend image, not the workers image.

    Expected JSON payload:
    {
        "summary_profile_id": str,
        "summarize_file_path": str,
        "org_id": str
    }
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    summary_profile_id = data.get("summary_profile_id", "")
    summarize_file_path = data.get("summarize_file_path", "")
    org_id = data.get("org_id", "")

    if not summary_profile_id or not summarize_file_path or not org_id:
        return JsonResponse(
            {
                "success": False,
                "error": "summary_profile_id, summarize_file_path, and org_id are required",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from utils.file_storage.constants import FileStorageKeys

        from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
        from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import (
            PromptIdeBaseTool,
        )
        from unstract.sdk1.constants import LogLevel
        from unstract.sdk1.file_storage.constants import StorageType
        from unstract.sdk1.file_storage.env_helper import EnvHelper
        from unstract.sdk1.utils.indexing import IndexingUtils

        profile = ProfileManager.objects.get(pk=summary_profile_id)
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
        doc_id = IndexingUtils.generate_index_key(
            vector_db=str(profile.vector_store_id),
            embedding=str(profile.embedding_model_id),
            x2text=str(profile.x2text_id),
            chunk_size="0",
            chunk_overlap=str(profile.chunk_overlap),
            file_path=summarize_file_path,
            fs=fs_instance,
            tool=util,
        )
        return JsonResponse({"success": True, "data": {"doc_id": doc_id}})

    except Exception as e:
        logger.exception("summary_index_key internal API failed")
        return JsonResponse(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
