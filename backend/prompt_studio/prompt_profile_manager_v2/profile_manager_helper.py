from prompt_studio.prompt_profile_manager_v2.models import ProfileManager


class ProfileManagerHelper:
    @classmethod
    def get_profile_manager(cls, profile_manager_id: str) -> ProfileManager:
        try:
            return ProfileManager.objects.get(profile_id=profile_manager_id)
        except ProfileManager.DoesNotExist:
            raise ValueError("ProfileManager does not exist.")
