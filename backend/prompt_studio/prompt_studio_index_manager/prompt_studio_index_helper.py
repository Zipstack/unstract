import json
import logging

from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio_document_manager.models import DocumentManager

from .models import IndexManager

logger = logging.getLogger(__name__)


class PromptStudioIndexHelper:

    @staticmethod
    def handle_index_manager(
        document_id: str,
        is_summary: bool,
        profile_manager: ProfileManager,
        doc_id: str
    ):
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)

        index_id = "raw_index_id"
        if is_summary:
            index_id = "summarize_index_id"

        try:
            index_manager: IndexManager = IndexManager.objects.get(**{
                "document_manager": document,
                "profile_manager": profile_manager,
            })
        except Exception:
            index_manager = None

        args: dict = {
            f'{index_id}': doc_id,
        }

        index_ids_list = []
        if index_manager:
            index_ids = index_manager.index_ids_history
            index_ids_list = json.loads(index_ids) if index_ids else []
            if doc_id not in index_ids:
                index_ids_list.append(doc_id)
        else:
            index_ids_list.append(doc_id)

        args["index_ids_history"] = json.dumps(index_ids_list)

        if index_manager:
            result: IndexManager = IndexManager.objects.filter(
                index_manager_id=index_manager.index_manager_id).update(**args)
        else:
            args["document_manager"] = document
            args["profile_manager"] = profile_manager
            result: IndexManager = IndexManager.objects.create(**args)
        return result
