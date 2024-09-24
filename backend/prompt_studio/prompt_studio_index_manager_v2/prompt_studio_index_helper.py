import json
import logging

from django.db import transaction
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.exceptions import IndexingAPIError
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager

from .models import IndexManager

logger = logging.getLogger(__name__)


class PromptStudioIndexHelper:
    @staticmethod
    def handle_index_manager(
        document_id: str,
        is_summary: bool,
        profile_manager: ProfileManager,
        doc_id: str,
    ) -> IndexManager:
        try:

            with transaction.atomic():

                document: DocumentManager = DocumentManager.objects.get(pk=document_id)

                index_id = "raw_index_id"
                if is_summary:
                    index_id = "summarize_index_id"

                args: dict[str, str] = dict()
                args["document_manager"] = document
                args["profile_manager"] = profile_manager

                # Create or get the existing record for this document and
                # profile combo
                index_manager, success = IndexManager.objects.get_or_create(**args)

                if success:
                    logger.info(
                        f"Index manager doc_id: {doc_id} for "
                        f"profile {profile_manager.profile_id} created"
                    )
                else:
                    logger.info(
                        f"Index manager doc_id: {doc_id} for "
                        f"profile {profile_manager.profile_id} updated"
                    )

                index_ids = index_manager.index_ids_history
                if not isinstance(index_ids, list):
                    index_ids_list = json.loads(index_ids) if index_ids else []
                else:
                    index_ids_list = index_ids
                if doc_id not in index_ids:
                    index_ids_list.append(doc_id)

                args[index_id] = doc_id
                args["index_ids_history"] = json.dumps(index_ids_list)

                # Update the record with the index id
                result: IndexManager = IndexManager.objects.filter(
                    index_manager_id=index_manager.index_manager_id
                ).update(**args)
            return result
        except Exception as e:
            transaction.rollback()
            raise IndexingAPIError("Error updating indexing status") from e
