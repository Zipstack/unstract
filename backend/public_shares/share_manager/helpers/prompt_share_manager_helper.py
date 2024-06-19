from prompt_studio.prompt_studio_core.prompt_studio_helper import PromptStudioHelper
from public_shares.share_manager.exceptions import ShareManagerException
from public_shares.share_manager.models import ShareManager


class PromptShareManagerHelper:

    @staticmethod
    def unlink_prompt_studio(share_id: str) -> None:
        tool = PromptStudioHelper.fetch_shared_project_instance(share_id)
        if tool.share_id:
            tool.share_id = None
            tool.save()
        else:
            raise ShareManagerException(
                "Public permissions already revoked for this project."
            )

    @staticmethod
    def link_prompt_studio(share: ShareManager, tool_id: str) -> None:
        tool = PromptStudioHelper.fetch_prompt_studio_project_instance(tool_id)
        if not tool.share_id:
            tool.share_id = share
            tool.save()
        else:
            raise ShareManagerException("Prompt sudio project already shared.")
