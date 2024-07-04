from django.apps import AppConfig


class CannedQuestionConfig(AppConfig):
    """Configuration for the canned Question.

    Args:
        AppConfig (_type_): _description_
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "pluggable_apps.apps.canned_question"
