import logging

from prompt_studio.prompt_studio_core.models import CustomTool
from .models import IndexManager
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_profile_manager.models import ProfileManager

logger = logging.getLogger(__name__)

class PromptStudioIndexHelper:
    
    @staticmethod
    def handle_index_manager(prompt_document_id: str, is_summary: bool, llm_profile: str, doc_id: str):
        document: DocumentManager = DocumentManager.objects.get(pk=prompt_document_id)
        profile_manager: ProfileManager = ProfileManager.objects.get(pk=llm_profile)
        
        IndexManager.objects.filter(
            document_manager=document
        ).update(is_active=False)
        
        
        profile = "raw_llm_profile"
        index_id = "raw_index_id"
        if is_summary:
            profile = "summarize_llm_profile"
            index_id = "summarize_index_id"
            
        index_manager: IndexManager = IndexManager.objects.get(**{
            "document_manager": document,
            f'{profile}': profile_manager,
            f'{index_id}': doc_id,
        })
        
        if index_manager:
            # Index Manager already exists
            return index_manager
        
        # Check if Index Manager with None doc_id is present
        index_manager: IndexManager = IndexManager.objects.get(**{
            "document_manager": document,
            f'{profile}': profile_manager,
            f'{index_id}': None,
        })
        
        if index_manager:
            # Index Manager with 'None' doc_id is present, so update the record with new doc_id
            return IndexManager.objects.update(**{
                "document_manager": document,
                f'{profile}': profile_manager,
                f'{index_id}': doc_id,
            })
        else:
            # Index Manager with doc_id is present, so create the record with new doc_id
            return IndexManager.objects.create(**{
                "document_manager": document,
                f'{profile}': profile_manager,
                f'{index_id}': doc_id,
            })