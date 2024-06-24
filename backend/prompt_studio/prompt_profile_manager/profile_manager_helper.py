from prompt_studio.prompt_profile_manager.models import ProfileManager


class ProfileManagerHelper:

    @classmethod
    def get_profile_manager(cls, profile_manager_id):
        try:
            return ProfileManager.objects.get(profile_id=profile_manager_id)
        except ProfileManager.DoesNotExist:
            raise ValueError(f"ProfileManager does not exist.")
        except Exception as e:
            raise RuntimeError(
                f"An error occurred while retrieving ProfileManager: {e}"
            )
