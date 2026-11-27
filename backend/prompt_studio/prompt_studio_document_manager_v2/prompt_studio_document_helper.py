import logging

from prompt_studio.prompt_studio_core_v2.models import CustomTool

from .models import DocumentManager

logger = logging.getLogger(__name__)


class PromptStudioDocumentHelper:
    @staticmethod
    def create(
        tool_id: str,
        document_name: str,
        size_bytes: int | None = None,
        page_count: int | None = None,
    ) -> DocumentManager:
        tool: CustomTool = CustomTool.objects.get(pk=tool_id)
        document: DocumentManager = DocumentManager.objects.create(
            tool=tool,
            document_name=document_name,
            size_bytes=size_bytes,
            page_count=page_count,
        )
        logger.info("Successfully created the record")
        return document

    @staticmethod
    def delete(document_id: str) -> None:
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        document.delete()
        logger.info("Successfully deleted the record")
